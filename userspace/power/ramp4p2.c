/*
 * ramp4p2: experiment - bring the 4P2 rail back up after 5V is plugged in
 * while running, after the Freescale BSP's ddi_power_Enable4p2() /
 * ddi_power_BringUp4p2Regulator() (root). Whole 32-bit stores.
 *
 *   ramp4p2        ramp CHARGE_4P2_ILIMIT from 0 to 480 mA in 100 mA steps
 *   ramp4p2 pwd    power 4P2 down for 10 ms (PWD_CHARGE_4P2), up again with
 *                  the limit at 0, then ramp
 *   ramp4p2 full   end in the state WinCE leaves when it boots with 5V
 *                  (DCDC4P2 0x10c01600, 5VCTRL as 0x24027111), from any state:
 *                  1. 5VCTRL: limit 0, 4P2 powered down
 *                  2. DCDC4P2: 4P2 on, DC-DC from 4P2 still off
 *                  3. 5VCTRL: 4P2 powered up, ILIMIT_EQ_ZERO cleared, ramp
 *                  4. after 10 ms, DCDC4P2: DC-DC from 4P2 on
 *                  (booted from the batteries alone, WinCE leaves 4P2 off:
 *                  DCDC4P2 0x00000018, 5VCTRL 0x24300115)
 * While 4P2 is down the DC-DC runs from the batteries, so do not use it on
 * weak batteries.
 * Build: arm-linux-gnueabi-gcc -O2 -march=armv5te -static -o ramp4p2 ramp4p2.c
 */
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#define POWER_BASE 0x80044000
#define VCTRL5 0x10
#define DCDC4P2 0x80
#define SHIFT 12
#define MASK 0x3fu
#define LIMIT (MASK << SHIFT)
#define PWD_CHARGE_4P2 (3u << 20) /* two bits on the i.MX28 */
#define ILIMIT_EQ_ZERO (1u << 2)
#define ENABLE_4P2 (1u << 23)
#define ENABLE_DCDC (1u << 22)
#define DCDC4P2_GOOD 0x10c01600u /* DROPOUT_CTRL 1, BO 4150 mV, TRG 4.2 V, CMPTRIP 0 */

static volatile uint32_t *p;

static void ramp(void)
{
	/* 100, 200, 300, 400, 480 mA (bits weigh 10, 20, 50, 100, 200, 400 mA) */
	static const uint32_t steps[] = { 0x08, 0x10, 0x18, 0x20, 0x27 };
	for (unsigned i = 0; i < sizeof steps / sizeof steps[0]; i++) {
		uint32_t v = p[VCTRL5 / 4];
		p[VCTRL5 / 4] = (v & ~LIMIT) | (steps[i] << SHIFT);
		usleep(2000);
	}
}

int main(int argc, char **argv)
{
	const char *mode = argc > 1 ? argv[1] : "";
	int fd = open("/dev/mem", O_RDWR | O_SYNC);
	if (fd < 0) {
		perror("/dev/mem");
		return 1;
	}
	p = mmap(NULL, 0x1000, PROT_READ | PROT_WRITE, MAP_SHARED, fd, POWER_BASE);
	if (p == MAP_FAILED) {
		perror("mmap");
		return 1;
	}
	uint32_t v = p[VCTRL5 / 4];
	printf("before: 5VCTRL %#010x DCDC4P2 %#010x\n", v, p[DCDC4P2 / 4]);

	if (!strcmp(mode, "full")) {
		p[VCTRL5 / 4] = (v & ~LIMIT) | PWD_CHARGE_4P2;
		usleep(2000);
		p[DCDC4P2 / 4] = DCDC4P2_GOOD & ~ENABLE_DCDC;
		usleep(2000);
		p[VCTRL5 / 4] = p[VCTRL5 / 4] & ~LIMIT & ~PWD_CHARGE_4P2 & ~ILIMIT_EQ_ZERO;
		usleep(2000);
		ramp();
		usleep(10000);
		p[DCDC4P2 / 4] = DCDC4P2_GOOD;
	} else {
		if (!strcmp(mode, "pwd")) {
			p[VCTRL5 / 4] = (v & ~LIMIT) | PWD_CHARGE_4P2;
			usleep(10000);
			p[VCTRL5 / 4] = v & ~LIMIT & ~PWD_CHARGE_4P2;
			usleep(2000);
		} else {
			p[VCTRL5 / 4] = v & ~LIMIT;
			usleep(2000);
		}
		ramp();
	}
	printf("after:  5VCTRL %#010x DCDC4P2 %#010x\n", p[VCTRL5 / 4], p[DCDC4P2 / 4]);
	return 0;
}
