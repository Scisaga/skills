/* Runs the actual recognizer with fake time/window metadata; opens no display. */
#define main tablet_bridge_application_main
#define clock_gettime controlled_clock_gettime
#include "../assets/desktop/guest/tablet-touch-longpress.c"
#undef main
#undef clock_gettime
#include <assert.h>

static double test_time;
static const char *test_class = "Xfdesktop";
int controlled_clock_gettime(clockid_t clock_id, struct timespec *value) {
    (void)clock_id; value->tv_sec = (time_t)test_time;
    value->tv_nsec = (long)((test_time - value->tv_sec) * 1000000000);
    return 0;
}
Status XGetClassHint(Display *d, Window w, XClassHint *hint) {
    (void)d; (void)w; hint->res_name = strdup(test_class); hint->res_class = strdup(test_class); return 1;
}
Bool XTranslateCoordinates(Display *d, Window a, Window b, int x, int y, int *ox, int *oy, Window *child) {
    (void)d;(void)a;(void)b;(void)x;(void)y;(void)ox;(void)oy;*child=None;return False;
}
Bool XTestFakeButtonEvent(Display *d, unsigned int button, Bool press, unsigned long delay) {
    (void)d;(void)press;(void)delay;
    assert(button == 3); /* Ordinary left clicks must never be synthesized. */
    return True;
}
static void reset(void) {
    contact_count=0;armed=0;pending_at=0;test_time=0;device_count=1;root=1;width=1000;height=1000;
    devices[0]=(TouchDevice){.id=42,.valid=3,.min={0,0},.max={999,999},.current={300,400}};
}
static XIRawEvent event(int detail, double *values, unsigned char *mask) {
    XIRawEvent value={0};value.sourceid=42;value.detail=detail;value.raw_values=values;
    value.valuators.mask_len=1;value.valuators.mask=mask;return value;
}
int main(void) {
    double values[]={300,400};unsigned char mask[]={3};XIRawEvent first=event(1,values,mask),second=event(2,values,mask);
    hold_ms=500;move_px=24;
    reset();touch(&first,XI_RawTouchBegin);test_time=.6;touch(&first,XI_RawTouchEnd);assert(pending_at>0);
    reset();touch(&first,XI_RawTouchBegin);test_time=.2;touch(&first,XI_RawTouchEnd);assert(pending_at==0);
    reset();touch(&first,XI_RawTouchBegin);values[0]=380;touch(&first,XI_RawTouchUpdate);test_time=.8;touch(&first,XI_RawTouchEnd);assert(pending_at==0);values[0]=300;
    reset();touch(&first,XI_RawTouchBegin);touch(&second,XI_RawTouchBegin);test_time=.8;touch(&second,XI_RawTouchEnd);touch(&first,XI_RawTouchEnd);assert(pending_at==0 && contact_count==0);
    reset();test_class="Thunar";touch(&first,XI_RawTouchBegin);test_time=.6;touch(&first,XI_RawTouchEnd);assert(pending_at>0);
    reset();test_class="Chromium";touch(&first,XI_RawTouchBegin);test_time=.8;touch(&first,XI_RawTouchEnd);assert(pending_at==0);
    reset();test_class="Code";touch(&first,XI_RawTouchBegin);test_time=.8;touch(&first,XI_RawTouchEnd);assert(pending_at==0);
    puts("PASS: long press, short tap, movement, multiple contacts and application scope");
    return 0;
}
