// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * mem-latency.c - la latenza di una lettura dalla DRAM, in ns: una catena di
 * puntatori, una per riga di cache, in ordine casuale in un buffer molto piu'
 * grande della cache, seguita per milioni di passi. Ogni lettura dipende dalla
 * precedente, quindi il tempo per passo e' la latenza di una lettura dalla
 * memoria, prefetch esclusi. Serve a confrontare due firmware sulla stessa
 * macchina (mrc.bin e la RAM init nativa, docs/raminit.md): stesso kernel,
 * stesso stato (sulla corrente o a batteria), macchina a riposo.
 *
 *   gcc -O2 -o mem-latency tools/mem-latency.c
 *   ./mem-latency             # 512 MiB, 9 misure
 *   ./mem-latency 1024 15     # MiB del buffer, numero di misure
 *
 * Le pagine da 2 MiB (madvise, se il kernel le concede) tengono fuori i miss
 * della TLB. Si confrontano le mediane: la minima dice quanto e' stabile.
 */
#define _GNU_SOURCE
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <time.h>

#define LINE	64
#define STEPS	(20 * 1000 * 1000)

static uint64_t rng = 0x9e3779b97f4a7c15ull;

static uint64_t next_random(void)
{
	rng ^= rng << 13;
	rng ^= rng >> 7;
	rng ^= rng << 17;
	return rng;
}

static double seconds(void)
{
	struct timespec t;
	clock_gettime(CLOCK_MONOTONIC, &t);
	return t.tv_sec + t.tv_nsec * 1e-9;
}

static int compare(const void *a, const void *b)
{
	const double x = *(const double *)a, y = *(const double *)b;
	return (x > y) - (x < y);
}

int main(int argc, char **argv)
{
	const size_t mib = argc > 1 ? strtoul(argv[1], NULL, 0) : 512;
	const int runs = argc > 2 ? atoi(argv[2]) : 9;
	const size_t size = mib << 20, lines = size / LINE;
	if (mib < 64 || runs < 1 || lines > UINT32_MAX) {
		fprintf(stderr, "uso: %s [MiB, almeno 64] [misure]\n", argv[0]);
		return 1;
	}
	char *buf = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	uint32_t *order = malloc(lines * sizeof(*order));
	double *ns = malloc(runs * sizeof(*ns));
	if (buf == MAP_FAILED || !order || !ns) {
		perror("memoria");
		return 1;
	}
	madvise(buf, size, MADV_HUGEPAGE);

	/* Le righe in ordine casuale (Fisher-Yates), legate in un unico ciclo */
	for (size_t i = 0; i < lines; i++)
		order[i] = i;
	for (size_t i = lines - 1; i > 0; i--) {
		const size_t j = next_random() % (i + 1);
		const uint32_t t = order[i];
		order[i] = order[j];
		order[j] = t;
	}
	for (size_t i = 0; i < lines; i++)
		*(char **)(buf + (size_t)order[i] * LINE) = buf + (size_t)order[(i + 1) % lines] * LINE;
	char **p = (char **)(buf + (size_t)order[0] * LINE);
	free(order);

	/* Un giro a vuoto, poi le misure */
	for (int r = -1; r < runs; r++) {
		const double t0 = seconds();
		for (long i = 0; i < STEPS; i++)
			p = (char **)*p;
		const double t1 = seconds();
		if (r >= 0)
			ns[r] = (t1 - t0) * 1e9 / STEPS;
	}
	qsort(ns, runs, sizeof(*ns), compare);
	printf("latenza DRAM: mediana %.2f ns, minima %.2f ns (%d misure, %zu MiB)%s\n",
	       ns[runs / 2], ns[0], runs, mib, p ? "" : " ");
	return 0;
}
