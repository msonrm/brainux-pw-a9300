/*
 * i.MX28 の SAIF0 を /dev/mem から直接動かす試験用プログラム（Brain 上で root で動かす）。
 * 設定値は WinCE の ymu818_wavdev.dll / CSPDDK.dll をエミュレーションして得たもの。
 *
 *   saif status                 クロックと SAIF0 のレジスタを表示
 *   saif setup                  SAIF0 のクロックを 22.5792MHz (512fs) にし、送信マスター・I2S・16bit で RUN
 *   saif tone HZ SEC AMP        正弦波を PIO で送る（AMP は 0..1、試験中は 0.3 まで）
 *   saif off                    RUN を止めてクロックを止める
 *
 * build: arm-linux-gnueabi-gcc -O2 -static -march=armv5te -o saif saif.c -lm
 */
#include <fcntl.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sched.h>
#include <time.h>
#include <unistd.h>

#define CLKCTRL_BASE 0x80040000
#define DIGCTL_BASE  0x8001c000
#define SAIF0_BASE   0x80042000

/* CLKCTRL */
#define PLL0CTRL0        0x000
#define PLL0_POWER       (1u << 17)
#define CLK_SAIF0        0x100
#define CLK_SAIF0_GATE   (1u << 31)
#define CLK_SAIF0_BUSY   (1u << 29)
#define CLK_SAIF0_FRAC   (1u << 16)
#define CLKSEQ           0x1d0
#define CLKSEQ_BYP_SAIF0 (1u << 0)

/* DIGCTL */
#define DIGCTL_CTRL      0x000
#define SAIF_CLKMUX_MASK (3u << 10)
#define SAIF_CLKMUX_VAL  (2u << 10)

/* SAIF（mxs-saif.h と同じ定義） */
#define SAIF_CTRL        0x00
#define SAIF_STAT        0x10
#define SAIF_DATA        0x20
#define SAIF_VERSION     0x30
#define CTRL_SFTRST      (1u << 31)
#define CTRL_CLKGATE     (1u << 30)
#define CTRL_DELAY       (1u << 11)
#define CTRL_RUN         (1u << 0)
#define STAT_DMA_PREQ    (1u << 16)
#define STAT_UNDERFLOW   (1u << 6)
#define STAT_OVERFLOW    (1u << 5)
#define STAT_SERVICE     (1u << 4)

#define SET 0x4
#define CLR 0x8

#define FS 44100
#define SAIF0_DIV 3083 /* 480MHz * 3083 / 65536 = 22.5806MHz ~= 512 * 44100 */

static volatile uint32_t *clk, *dig, *saif;

static volatile uint32_t *map(int fd, off_t base)
{
	void *p = mmap(NULL, 0x2000, PROT_READ | PROT_WRITE, MAP_SHARED, fd, base);
	if (p == MAP_FAILED) {
		perror("mmap /dev/mem");
		exit(1);
	}
	return p;
}

#define R(b, off)    ((b)[(off) / 4])
#define W(b, off, v) ((b)[(off) / 4] = (v))

static void status(void)
{
	uint32_t s0 = R(clk, CLK_SAIF0);
	printf("PLL0CTRL0  %08x (power %s)\n", R(clk, PLL0CTRL0), R(clk, PLL0CTRL0) & PLL0_POWER ? "on" : "off");
	printf("CLK_SAIF0  %08x (gate %d, busy %d, frac %d, div %u -> %.1f Hz)\n", s0,
	       !!(s0 & CLK_SAIF0_GATE), !!(s0 & CLK_SAIF0_BUSY), !!(s0 & CLK_SAIF0_FRAC), s0 & 0xffff,
	       (s0 & CLK_SAIF0_FRAC) ? 480e6 * (s0 & 0xffff) / 65536.0 : 0.0);
	printf("CLKSEQ     %08x (bypass_saif0 %d)\n", R(clk, CLKSEQ), R(clk, CLKSEQ) & CLKSEQ_BYP_SAIF0);
	printf("DIGCTL     %08x (saif_clkmux %u)\n", R(dig, DIGCTL_CTRL), (R(dig, DIGCTL_CTRL) >> 10) & 3);
	printf("SAIF0 CTRL %08x STAT %08x VERSION %08x\n", R(saif, SAIF_CTRL), R(saif, SAIF_STAT), R(saif, SAIF_VERSION));
}

static void setup(void)
{
	int i;

	if (!(R(clk, PLL0CTRL0) & PLL0_POWER)) {
		printf("PLL0 is off, powering on\n");
		W(clk, PLL0CTRL0 + SET, PLL0_POWER);
		usleep(100);
	}
	/* WinCE と同じ順: BYPASS_SAIF0 を解除してから分数分周を設定 */
	W(clk, CLKSEQ + CLR, CLKSEQ_BYP_SAIF0);
	W(clk, CLK_SAIF0, CLK_SAIF0_FRAC);
	W(clk, CLK_SAIF0, CLK_SAIF0_FRAC | SAIF0_DIV);
	for (i = 0; i < 1000 && (R(clk, CLK_SAIF0) & CLK_SAIF0_BUSY); i++)
		usleep(10);
	if (R(clk, CLK_SAIF0) & CLK_SAIF0_BUSY)
		fprintf(stderr, "warning: CLK_SAIF0 still busy\n");

	W(dig, DIGCTL_CTRL + CLR, SAIF_CLKMUX_MASK);
	W(dig, DIGCTL_CTRL + SET, SAIF_CLKMUX_VAL);

	/* SAIF0: リセットを抜けて、送信・マスター・I2S (DELAY)・16bit・512fs で RUN（MCLK を出す） */
	W(saif, SAIF_CTRL + SET, CTRL_SFTRST);
	W(saif, SAIF_CTRL + CLR, CTRL_SFTRST);
	W(saif, SAIF_CTRL + CLR, CTRL_CLKGATE);
	W(saif, SAIF_CTRL, CTRL_DELAY | CTRL_RUN);
	status();
}

static double now(void)
{
	struct timespec ts;
	clock_gettime(CLOCK_MONOTONIC, &ts);
	return ts.tv_sec + ts.tv_nsec * 1e-9;
}

#define TABLE_BITS 12
#define TABLE_SIZE (1 << TABLE_BITS)

/*
 * 浮動小数点の専用回路がないので、送り出し中は整数だけで計算する。
 * 正弦波は事前に表にし、位相を足していく (DDS)。時刻の確認は 256 フレームに 1 回。
 */
static void tone(double hz, double sec, double amp)
{
	static int16_t table[TABLE_SIZE];
	long n = (long)(sec * FS), i, underflows = 0, retries = 0;
	long fade = FS / 50; /* 20ms のフェードでクリックを抑える */
	uint32_t phase = 0, step = (uint32_t)(hz * 4294967296.0 / FS);
	struct sched_param sp = { .sched_priority = 50 };
	double t0, elapsed, limit = sec * 3 + 1;
	int k, aborted = 0;

	if (amp < 0 || amp > 0.3) {
		fprintf(stderr, "AMP must be 0..0.3 while testing\n");
		exit(1);
	}
	if (!(R(saif, SAIF_CTRL) & CTRL_RUN)) {
		fprintf(stderr, "SAIF0 is not running; run 'saif setup' first\n");
		exit(1);
	}
	for (k = 0; k < TABLE_SIZE; k++)
		table[k] = (int16_t)(32767.0 * amp * sin(2 * M_PI * k / TABLE_SIZE));
	if (sched_setscheduler(0, SCHED_FIFO, &sp))
		perror("sched_setscheduler (continuing without realtime)");

	W(saif, SAIF_STAT + CLR, STAT_UNDERFLOW | STAT_OVERFLOW);
	t0 = now();
	for (i = 0; i < n; i++) {
		int32_t s = table[phase >> (32 - TABLE_BITS)];
		uint32_t w, st;
		long tries = 0;

		phase += step;
		if (i < fade)
			s = s * i / fade;
		else if (n - i < fade)
			s = s * (n - i) / fade;
		w = ((uint32_t)(uint16_t)s << 16) | (uint16_t)s;

		/*
		 * FIFO は 4 フレームしかなく、DMA_PREQ は PIO では当てにならない。
		 * 書いてあふれたら (OVERFLOW) 書き直す。送る速さは SAIF のクロックで決まる。
		 */
		for (;;) {
			W(saif, SAIF_DATA, w);
			st = R(saif, SAIF_STAT);
			if (!(st & STAT_OVERFLOW))
				break;
			W(saif, SAIF_STAT + CLR, STAT_OVERFLOW);
			if (++tries > 1000000)
				break;
		}
		retries += tries;
		if (st & STAT_UNDERFLOW) {
			underflows++;
			W(saif, SAIF_STAT + CLR, STAT_UNDERFLOW);
		}
		/* 止まらなくなったときの保険。時刻の取得は重いので 4096 フレームに 1 回 */
		if ((i & 4095) == 0 && now() - t0 > limit) {
			aborted = 1;
			break;
		}
	}
	elapsed = now() - t0;
	sp.sched_priority = 0;
	sched_setscheduler(0, SCHED_OTHER, &sp);
	printf("sent %ld/%ld frames in %.2f s (expected %.2f s), underflows %ld, overflow retries %ld%s\n",
	       i, n, elapsed, sec, underflows, retries, aborted ? ", ABORTED (time limit)" : "");
}

/* SAIF0 の STAT を読む速さ、FIFO の深さ、DMA_PREQ の挙動を測る（無音のデータを書く） */
static void diag(void)
{
	uint32_t st[64], prev;
	double t0, t;
	long i, reads;
	int k;

	if (!(R(saif, SAIF_CTRL) & CTRL_RUN)) {
		fprintf(stderr, "SAIF0 is not running; run 'saif setup' first\n");
		exit(1);
	}
	t0 = now();
	for (i = 0; i < 100000; i++)
		(void)R(saif, SAIF_STAT);
	t = now() - t0;
	printf("STAT read: %.0f ns each\n", t / 100000 * 1e9);
	printf("STAT idle: %08x\n", R(saif, SAIF_STAT));

	/* FIFO の深さ: 空にしてから続けて書き、何個目で OVERFLOW が立つか */
	for (k = 0; k < 3; k++) {
		int m;

		usleep(5000); /* 空になるまで待つ */
		W(saif, SAIF_STAT + CLR, STAT_UNDERFLOW | STAT_OVERFLOW);
		for (m = 1; m <= 64; m++) {
			W(saif, SAIF_DATA, 0);
			if (R(saif, SAIF_STAT) & STAT_OVERFLOW)
				break;
		}
		printf("overflow after %d writes (STAT %08x)\n", m, R(saif, SAIF_STAT));
	}
	/* 一気に 8 個書いて、UNDERFLOW が立つまでの時間（FIFO が空になる速さ） */
	usleep(5000);
	for (k = 0; k < 8; k++)
		W(saif, SAIF_DATA, 0);
	W(saif, SAIF_STAT + CLR, STAT_UNDERFLOW | STAT_OVERFLOW);
	t0 = now();
	while (!(R(saif, SAIF_STAT) & STAT_UNDERFLOW) && now() - t0 < 0.01)
		;
	printf("8 frames drained in %.1f us (%.1f us expected at 44.1kHz)\n", (now() - t0) * 1e6, 8e6 / FS);

	/* 続けて書き、各回の直後の STAT を記録 */
	for (k = 0; k < 64; k++) {
		W(saif, SAIF_DATA, 0);
		st[k] = R(saif, SAIF_STAT);
	}
	for (k = 0; k < 64; k++)
		printf("%s%08x", k % 8 ? " " : "\n  after write ", st[k]);
	printf("\n");

	/* 書くのをやめて 20ms、STAT の変化を時刻つきで記録 */
	t0 = now();
	prev = R(saif, SAIF_STAT);
	printf("  t=%8.1f us STAT %08x\n", 0.0, prev);
	reads = 0;
	while ((t = now() - t0) < 0.02) {
		uint32_t v = R(saif, SAIF_STAT);

		reads++;
		if (v != prev) {
			printf("  t=%8.1f us STAT %08x\n", t * 1e6, v);
			prev = v;
		}
	}
	printf("  (%ld reads in 20ms)\n", reads);

	/* 1 フレーム書くたびに PREQ を待つ方式で 4410 フレーム（0.1 秒分）送って時間を測る */
	W(saif, SAIF_STAT + CLR, STAT_UNDERFLOW);
	{
		long spins = 0, maxspin = 0, under = 0;

		t0 = now();
		for (i = 0; i < 4410; i++) {
			long sp = 0;

			while (!(R(saif, SAIF_STAT) & STAT_DMA_PREQ) && sp < 200000)
				sp++;
			spins += sp;
			if (sp > maxspin)
				maxspin = sp;
			W(saif, SAIF_DATA, 0);
			if (R(saif, SAIF_STAT) & STAT_UNDERFLOW) {
				under++;
				W(saif, SAIF_STAT + CLR, STAT_UNDERFLOW);
			}
		}
		t = now() - t0;
		printf("4410 frames paced by PREQ: %.3f s (0.100 expected), avg spin %ld, max spin %ld, underflows %ld\n",
		       t, spins / 4410, maxspin, under);
	}
}

static void off(void)
{
	W(saif, SAIF_CTRL + CLR, CTRL_RUN);
	W(saif, SAIF_CTRL + SET, CTRL_CLKGATE);
	W(clk, CLK_SAIF0, R(clk, CLK_SAIF0) | CLK_SAIF0_GATE);
	status();
}

int main(int argc, char **argv)
{
	int fd;

	if (argc < 2) {
		fprintf(stderr, "usage: saif status|setup|tone HZ SEC AMP|diag|off\n");
		return 1;
	}
	setvbuf(stdout, NULL, _IONBF, 0); /* 打ち切られても途中までの出力が残るように */
	fd = open("/dev/mem", O_RDWR | O_SYNC);
	if (fd < 0) {
		perror("/dev/mem");
		return 1;
	}
	clk = map(fd, CLKCTRL_BASE);
	dig = map(fd, DIGCTL_BASE);
	saif = map(fd, SAIF0_BASE);

	if (!strcmp(argv[1], "status"))
		status();
	else if (!strcmp(argv[1], "setup"))
		setup();
	else if (!strcmp(argv[1], "tone") && argc == 5)
		tone(atof(argv[2]), atof(argv[3]), atof(argv[4]));
	else if (!strcmp(argv[1], "diag"))
		diag();
	else if (!strcmp(argv[1], "off"))
		off();
	else {
		fprintf(stderr, "bad arguments\n");
		return 1;
	}
	return 0;
}
