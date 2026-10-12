/*
 * battpins: print the four battery-watch GPIO inputs of Brain PW-A9300 (root).
 * GPIO4_4, GPIO4_6, GPIO4_7, GPIO4_8 read 0 when the batteries run low
 * (all 0 on nearly empty alkaline cells, all 1 on fresh ones).
 * Reads HW_PINCTRL_DIN4 through /dev/mem; changes nothing.
 * Output: "4_4=1 4_6=1 4_7=1 4_8=1"
 * Build: arm-linux-gnueabi-gcc -O2 -static -o battpins battpins.c
 */
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/mman.h>
#include <unistd.h>

#define PINCTRL_BASE 0x80018000
#define DIN4 0x940

int main(void)
{
	int fd = open("/dev/mem", O_RDONLY | O_SYNC);
	if (fd < 0) {
		perror("/dev/mem");
		return 1;
	}
	volatile uint32_t *p = mmap(NULL, 0x1000, PROT_READ, MAP_SHARED, fd, PINCTRL_BASE);
	if (p == MAP_FAILED) {
		perror("mmap");
		return 1;
	}
	uint32_t din = p[DIN4 / 4];
	printf("4_4=%u 4_6=%u 4_7=%u 4_8=%u\n",
	       (din >> 4) & 1, (din >> 6) & 1, (din >> 7) & 1, (din >> 8) & 1);
	return 0;
}
