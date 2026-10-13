/*
 * brain-5v-ilimit: let the i.MX28 take up to 480 mA from 5V (root).
 * Linux leaves HW_POWER_5VCTRL as the boot loader left it, and that depends
 * on whether 5V was there at power-on (CHARGE_4P2_ILIMIT = 0x08, 100 mA) or
 * plugged in later (0x27, 480 mA). Above the limit the DC-DC tops up from the
 * batteries. The limit only matters while 5V is present, so this sets it at
 * boot either way. It only raises the limit, never lowers it (lowering it
 * under load on weak batteries brought the system down, 2026-10-13).
 * One 32-bit store through /dev/mem, so the register never holds a partial
 * value.
 * Build: arm-linux-gnueabi-gcc -O2 -static -o brain-5v-ilimit brain-5v-ilimit.c
 */
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/mman.h>
#include <unistd.h>

#define POWER_BASE 0x80044000
#define VCTRL5 0x10
#define SHIFT 12
#define MASK 0x3fu
#define WANT 0x27u

int main(void)
{
	int fd = open("/dev/mem", O_RDWR | O_SYNC);
	if (fd < 0) {
		perror("/dev/mem");
		return 1;
	}
	volatile uint32_t *p = mmap(NULL, 0x1000, PROT_READ | PROT_WRITE, MAP_SHARED, fd, POWER_BASE);
	if (p == MAP_FAILED) {
		perror("mmap");
		return 1;
	}
	uint32_t v = p[VCTRL5 / 4];
	uint32_t cur = (v >> SHIFT) & MASK;
	if (cur >= WANT) {
		printf("5VCTRL %#010x (4P2 limit %#x, left as is)\n", v, cur);
		return 0;
	}
	uint32_t nv = (v & ~(MASK << SHIFT)) | (WANT << SHIFT);
	p[VCTRL5 / 4] = nv;
	printf("5VCTRL %#010x -> %#010x (4P2 limit %#x -> %#x)\n", v, p[VCTRL5 / 4], cur, WANT);
	return 0;
}
