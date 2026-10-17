/*
 * battvolt: read the battery voltage of Brain PW-A9300 on LRADC ch1 (root).
 * GPIO3_2 (AUART0_CTS pad, used by no driver) switches a FET that connects
 * the batteries to LRADC1 (brain-hackers Scrapbox "PW-A9300"). Turn it on
 * only for the reading:
 * set GPIO3_2 -> wait 2 ms -> read in_voltage1_raw 5 times -> clear GPIO3_2.
 * ch1 is read with DIVIDE_BY_TWO (in_voltage1_scale = 0.903320310), set here
 * if needed; nothing else uses ch1.
 * Refuses to touch the pin unless it is muxed as GPIO and driven as output.
 * Output: "bvraw=3161 bv=2855" (bv = raw * scale in mV, i.e. assuming the
 * board divides by 1; the real ratio is not known yet, so keep the raw value)
 * Build: arm-linux-gnueabi-gcc -O2 -march=armv5te -static -o battvolt battvolt.c
 */
#include <fcntl.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/mman.h>
#include <unistd.h>

#define PINCTRL_BASE 0x80018000
#define MUXSEL6 0x160 /* bank 3, pins 0-15, 2 bits each */
#define DOUT3_SET 0x734
#define DOUT3_CLR 0x738
#define DOE3 0xb30
#define PIN 2

#define IIO "/sys/bus/iio/devices/iio:device0/"
#define SCALE_DIV2 "0.903320310"

static int read_raw(void)
{
	char buf[32];
	int fd = open(IIO "in_voltage1_raw", O_RDONLY);
	if (fd < 0)
		return -1;
	ssize_t n = read(fd, buf, sizeof buf - 1);
	close(fd);
	if (n <= 0)
		return -1;
	buf[n] = 0;
	return atoi(buf);
}

static double scale(void)
{
	char buf[32] = "";
	FILE *f = fopen(IIO "in_voltage1_scale", "r+");
	if (!f)
		return -1;
	if (!fgets(buf, sizeof buf, f) || strtod(buf, NULL) < 0.9) {
		rewind(f);
		fputs(SCALE_DIV2, f);
		fclose(f);
		f = fopen(IIO "in_voltage1_scale", "r");
		if (!f || !fgets(buf, sizeof buf, f))
			return -1;
	}
	fclose(f);
	return strtod(buf, NULL);
}

int main(void)
{
	int fd = open("/dev/mem", O_RDWR | O_SYNC);
	if (fd < 0) {
		perror("/dev/mem");
		return 1;
	}
	volatile uint32_t *p = mmap(NULL, 0x1000, PROT_READ | PROT_WRITE, MAP_SHARED, fd, PINCTRL_BASE);
	if (p == MAP_FAILED) {
		perror("mmap");
		return 1;
	}
	if (((p[MUXSEL6 / 4] >> (PIN * 2)) & 3) != 3 || !((p[DOE3 / 4] >> PIN) & 1)) {
		fprintf(stderr, "battvolt: GPIO3_2 is not a GPIO output; not touching it\n");
		return 1;
	}
	/* one at a time: another run clearing the pin would spoil our reading */
	int lk = open("/run/battvolt.lock", O_RDWR | O_CREAT, 0600);
	if (lk >= 0)
		flock(lk, LOCK_EX);
	double s = scale();
	if (s < 0.9) {
		fprintf(stderr, "battvolt: cannot set in_voltage1_scale\n");
		return 1;
	}

	/* keep the FET on for as short as possible, even if we get a signal */
	sigset_t all, old;
	sigfillset(&all);
	sigprocmask(SIG_BLOCK, &all, &old);
	p[DOUT3_SET / 4] = 1u << PIN;
	usleep(2000);
	int sum = 0, ok = 0;
	for (int i = 0; i < 5; i++) {
		int r = read_raw();
		if (r >= 0) {
			sum += r;
			ok++;
		}
	}
	p[DOUT3_CLR / 4] = 1u << PIN;
	sigprocmask(SIG_SETMASK, &old, NULL);

	if (!ok) {
		fprintf(stderr, "battvolt: cannot read in_voltage1_raw\n");
		return 1;
	}
	int raw = (sum + ok / 2) / ok;
	printf("bvraw=%d bv=%d\n", raw, (int)(raw * s + 0.5));
	return 0;
}
