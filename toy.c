#include <stdio.h>
__attribute__((noinline)) void roi_begin(void){ __asm__ volatile("":::"memory"); }
__attribute__((noinline)) void roi_end(void){ __asm__ volatile("":::"memory"); }
int main(){
  volatile long s=0;
  for(int i=0;i<1000;i++) s+=i;      // outside ROI
  roi_begin();
  for(int i=0;i<5000;i++) s+=i;      // inside ROI
  roi_end();
  printf("%ld\n",s);
}
