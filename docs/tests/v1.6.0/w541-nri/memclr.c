/* memclr.c: each thread allocates N MiB, touches it, then times memset(0) or rep stosb.
 * usage: memclr THREADS MIB {memset|stosb|nt} [cpu list comma-separated] */
#define _GNU_SOURCE
#include <pthread.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <immintrin.h>
static size_t n; static int mode; static pthread_barrier_t bar; static int cpus[64];
static double now(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec*1e-9;}
static void *run(void *a){
  long i=(long)a; cpu_set_t s; CPU_ZERO(&s); CPU_SET(cpus[i],&s); pthread_setaffinity_np(pthread_self(),sizeof s,&s);
  char *b=aligned_alloc(1<<21,n); memset(b,1,n);
  double best=1e9;
  for(int r=0;r<3;r++){
    pthread_barrier_wait(&bar); double t0=now();
    if(mode==0) memset(b,0,n);
    else if(mode==1){void*d=b;size_t c=n;__asm__ volatile("rep stosb":"+D"(d),"+c"(c):"a"(0):"memory");}
    else {__m256i z=_mm256_setzero_si256(); for(size_t k=0;k<n;k+=32)_mm256_stream_si256((__m256i*)(b+k),z); _mm_sfence();}
    double dt=now()-t0; if(dt<best)best=dt; pthread_barrier_wait(&bar);
  }
  printf("  thread %ld cpu %d: %.1f GB/s\n",i,cpus[i],n/best/1e9); free(b); return 0;}
int main(int c,char**v){int t=atoi(v[1]); n=(size_t)atol(v[2])<<20; mode=!strcmp(v[3],"memset")?0:!strcmp(v[3],"stosb")?1:2;
  for(int i=0;i<t;i++)cpus[i]=i; if(c>4){char*p=strtok(v[4],",");for(int i=0;p&&i<t;i++,p=strtok(0,","))cpus[i]=atoi(p);}
  pthread_barrier_init(&bar,0,t); pthread_t th[64]; double t0=now();
  for(long i=0;i<t;i++)pthread_create(&th[i],0,run,(void*)i); for(int i=0;i<t;i++)pthread_join(th[i],0);
  return 0;}
