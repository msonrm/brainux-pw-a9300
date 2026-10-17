/*
 * brain-5v-ilimit: keep the i.MX28 powered from 5V when 5V is there (root).
 *
 * 1. At start, let the SoC take up to 480 mA from 5V. Linux leaves
 *    HW_POWER_5VCTRL as the boot loader left it, and that depends on whether
 *    5V was there at power-on (CHARGE_4P2_ILIMIT = 0x08, 100 mA) or plugged in
 *    later (0x27, 480 mA). Above the limit the DC-DC tops up from the
 *    batteries. It only raises the limit here, never lowers it (lowering it
 *    under load on weak batteries brought the system down, 2026-10-13).
 * 2. Then wait for 5V to be plugged in while running (the keyboard controller
 *    reports it as SW_DOCK on brain-kbd-i2c). When 5V goes away the hardware
 *    moves to the batteries by itself, but when it comes back the 4P2 rail is
 *    not brought up again and the DC-DC keeps running from the batteries
 *    (2026-10-17). The Freescale BSP restarts 4P2 in software on every
 *    plug-in (ddi_power_Enable4p2). Do it the same way: power 4P2 down, turn
 *    it on in DCDC4P2, power it up with the limit at 0, ramp the limit to
 *    480 mA in 100 mA steps, then run the DC-DC from 4P2 (restart_4p2).
 *    To see whether it took, the 5V reading (LRADC ch15) is averaged before
 *    and after: it sags when the SoC draws from 5V again. Skipped when the
 *    battery-watch pins all read 0 (nearly empty cells; 4P2 off means running
 *    from them alone for a moment).
 * 3. After a plug-in, also start brain-wifi-reprobe: plugging the hub in
 *    often leaves the Wi-Fi stick without a driver (-11 while rtl8xxxu66
 *    writes the firmware), and the script power-cycles it then. It does
 *    nothing when the stick is fine.
 *
 * Every register write is one 32-bit store through /dev/mem.
 * Build: arm-linux-gnueabi-gcc -O2 -march=armv5te -static -o brain-5v-ilimit brain-5v-ilimit.c
 */
#include <dirent.h>
#include <fcntl.h>
#include <linux/input.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

#define POWER_BASE 0x80044000
#define VCTRL5 0x10
#define SHIFT 12
#define MASK 0x3fu
#define WANT 0x27u
#define PWD_CHARGE_4P2 (3u << 20) /* two bits on the i.MX28 */
#define ILIMIT_EQ_ZERO (1u << 2)
#define DCDC4P2 0x80
#define ENABLE_DCDC (1u << 22)
#define DCDC4P2_GOOD 0x10c01600u /* 4P2 and DC-DC from 4P2 on, DROPOUT_CTRL 1, BO 4150 mV */

#define PINCTRL_BASE 0x80018000
#define DIN4 0x940

#define KBD "brain-kbd-i2c"
#define IIO "/sys/bus/iio/devices/iio:device0/"

static volatile uint32_t *pw, *pin;

static void *map(int fd, off_t base)
{
	void *p = mmap(NULL, 0x1000, PROT_READ | PROT_WRITE, MAP_SHARED, fd, base);
	if (p == MAP_FAILED) {
		perror("mmap");
		exit(1);
	}
	return p;
}

static void raise_limit(void)
{
	uint32_t v = pw[VCTRL5 / 4];
	uint32_t cur = (v >> SHIFT) & MASK;
	if (cur >= WANT) {
		printf("5VCTRL %#010x (4P2 limit %#x, left as is), DCDC4P2 %#010x\n", v, cur, pw[DCDC4P2 / 4]);
		return;
	}
	pw[VCTRL5 / 4] = (v & ~(MASK << SHIFT)) | (WANT << SHIFT);
	printf("5VCTRL %#010x -> %#010x (4P2 limit %#x -> %#x), DCDC4P2 %#010x\n", v, pw[VCTRL5 / 4], cur, WANT, pw[DCDC4P2 / 4]);
}

/*
 * End in the state WinCE leaves when it boots with 5V (DCDC4P2 0x10c01600,
 * 5VCTRL as 0x24027111), from any state. Booted from the batteries alone,
 * WinCE leaves 4P2 off (DCDC4P2 0x00000018, 5VCTRL 0x24300115).
 */
static void restart_4p2(void)
{
	static const uint32_t steps[] = { 0x08, 0x10, 0x18, 0x20, WANT };

	/* 1. limit 0, 4P2 powered down */
	pw[VCTRL5 / 4] = (pw[VCTRL5 / 4] & ~(MASK << SHIFT)) | PWD_CHARGE_4P2;
	usleep(2000);
	/* 2. 4P2 on, DC-DC from 4P2 still off */
	pw[DCDC4P2 / 4] = DCDC4P2_GOOD & ~ENABLE_DCDC;
	usleep(2000);
	/* 3. 4P2 powered up, no forced zero limit, ramp the limit */
	pw[VCTRL5 / 4] = pw[VCTRL5 / 4] & ~(MASK << SHIFT) & ~PWD_CHARGE_4P2 & ~ILIMIT_EQ_ZERO;
	usleep(2000);
	for (unsigned i = 0; i < sizeof steps / sizeof steps[0]; i++) {
		uint32_t v = pw[VCTRL5 / 4] & ~(MASK << SHIFT);
		pw[VCTRL5 / 4] = v | (steps[i] << SHIFT);
		usleep(2000);
	}
	/* 4. DC-DC from 4P2 */
	usleep(10000);
	pw[DCDC4P2 / 4] = DCDC4P2_GOOD;
}

static double read_num(const char *path)
{
	char buf[32];
	int fd = open(path, O_RDONLY);
	if (fd < 0)
		return -1;
	ssize_t n = read(fd, buf, sizeof buf - 1);
	close(fd);
	if (n <= 0)
		return -1;
	buf[n] = 0;
	return strtod(buf, NULL);
}

/* average of the 5V reading over sec seconds, in mV */
static int vdd5v(double sec)
{
	double scale = read_num(IIO "in_voltage15_scale"), sum = 0;
	int n = 0;
	for (int i = 0; i < sec * 10; i++) {
		double r = read_num(IIO "in_voltage15_raw");
		if (r >= 0) {
			sum += r;
			n++;
		}
		usleep(100000);
	}
	return n && scale > 0 ? (int)(sum / n * scale + 0.5) : -1;
}

static int find_kbd(void)
{
	DIR *d = opendir("/dev/input");
	struct dirent *e;
	int fd = -1;
	if (!d)
		return -1;
	while (fd < 0 && (e = readdir(d))) {
		char path[300], name[64] = "";
		if (strncmp(e->d_name, "event", 5))
			continue;
		snprintf(path, sizeof path, "/dev/input/%s", e->d_name);
		int f = open(path, O_RDONLY);
		if (f < 0)
			continue;
		if (ioctl(f, EVIOCGNAME(sizeof name - 1), name) >= 0 && !strcmp(name, KBD))
			fd = f;
		else
			close(f);
	}
	closedir(d);
	return fd;
}

static int docked(int fd)
{
	unsigned long sw[1] = { 0 };
	if (ioctl(fd, EVIOCGSW(sizeof sw), sw) < 0)
		return -1;
	return (sw[0] >> SW_DOCK) & 1;
}

/* drop the events that came in while we were busy (contact bounce) */
static void drain(int fd)
{
	struct input_event ev;
	int fl = fcntl(fd, F_GETFL);
	fcntl(fd, F_SETFL, fl | O_NONBLOCK);
	while (read(fd, &ev, sizeof ev) == sizeof ev)
		;
	fcntl(fd, F_SETFL, fl);
}

static void on_plug(int fd)
{
	/* let the plug settle; a bouncing contact sends several events */
	sleep(1);
	if (docked(fd) != 1)
		return;
	uint32_t din = pin[DIN4 / 4];
	if (!((din >> 4) & 1) && !((din >> 6) & 1) && !((din >> 7) & 1) && !((din >> 8) & 1)) {
		printf("5V plugged in: battery pins 0000, 4P2 not restarted\n");
		fflush(stdout);
		return;
	}
	uint32_t c0 = pw[VCTRL5 / 4], d0 = pw[DCDC4P2 / 4];
	int before = vdd5v(1);
	restart_4p2();
	usleep(500000);
	int after = vdd5v(2);
	printf("5V plugged in: 4P2 restarted, 5VCTRL %#010x -> %#010x, DCDC4P2 %#010x -> %#010x, 5V %d -> %d mV (%s)\n",
	       c0, pw[VCTRL5 / 4], d0, pw[DCDC4P2 / 4], before, after,
	       before - after >= 80 ? "drawing from 5V again" : "no sag: check battcheck");
	fflush(stdout);
}

int main(void)
{
	int fd = open("/dev/mem", O_RDWR | O_SYNC);
	if (fd < 0) {
		perror("/dev/mem");
		return 1;
	}
	pw = map(fd, POWER_BASE);
	pin = map(fd, PINCTRL_BASE);
	raise_limit();
	fflush(stdout);

	for (;;) {
		int kbd = find_kbd();
		if (kbd < 0) {
			sleep(10);
			continue;
		}
		struct input_event ev;
		while (read(kbd, &ev, sizeof ev) == sizeof ev) {
			if (ev.type == EV_SW && ev.code == SW_DOCK && ev.value == 1) {
				on_plug(kbd);
				drain(kbd);
				/* fails if it is already running (woken by this plug-in): fine */
				(void)!system("systemd-run --no-block --collect --unit=brain-wifi-reprobe "
					      "/usr/local/bin/brain-wifi-reprobe >/dev/null 2>&1");
			}
		}
		close(kbd); /* the keyboard driver went away (inputlog.py); look again */
		sleep(2);
	}
}
