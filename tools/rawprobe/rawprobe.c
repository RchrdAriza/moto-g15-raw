// rawprobe: open a camera with a single RAW16 stream, run a repeating request, dump one frame.
// Usage: rawprobe <camera-id> <width> <height> <out.raw16> [raw16|yuv] [+preview]
// "+preview" adds a concurrent 1920x1080 YUV stream, like a camera app viewfinder.
#include <camera/NdkCameraManager.h>
#include <camera/NdkCameraDevice.h>
#include <camera/NdkCameraCaptureSession.h>
#include <media/NdkImageReader.h>
#include <dlfcn.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <unistd.h>

#define CHECK(x) do { camera_status_t s_ = (x); if (s_ != ACAMERA_OK) { fprintf(stderr, "%s -> %d\n", #x, s_); return 1; } } while (0)
#define CHECKM(x) do { media_status_t s_ = (x); if (s_ != AMEDIA_OK) { fprintf(stderr, "%s -> %d\n", #x, s_); return 1; } } while (0)

static void onDisconnected(void *ctx, ACameraDevice *d) { fprintf(stderr, "device disconnected\n"); }
static void onError(void *ctx, ACameraDevice *d, int err) { fprintf(stderr, "device error %d\n", err); }
static void onFailed(void *ctx, ACameraCaptureSession *s, ACaptureRequest *r, ACameraCaptureFailure *f) {
    fprintf(stderr, "capture failed: reason=%d frame=%lld\n", f->reason, (long long)f->frameNumber);
}
static void onSessClosed(void *c, ACameraCaptureSession *s) {}
static void onSessReady(void *c, ACameraCaptureSession *s) {}
static void onSessActive(void *c, ACameraCaptureSession *s) {}

int main(int argc, char **argv) {
    if (argc < 5) { fprintf(stderr, "usage: %s <id> <w> <h> <out> [raw16|yuv]\n", argv[0]); return 2; }
    const char *id = argv[1]; int w = atoi(argv[2]), h = atoi(argv[3]);
    int yuv = argc > 5 && argv[5][0] == 'y';
    int32_t format = yuv ? AIMAGE_FORMAT_YUV_420_888 : AIMAGE_FORMAT_RAW16;

    // Buffers and callbacks come back from cameraserver over binder; a bare executable needs a pool.
    // ABinderProcess_* is not in the public NDK headers, so resolve it from the device library.
    void *bnd = dlopen("libbinder_ndk.so", RTLD_NOW);
    bool (*setMax)(uint32_t) = bnd ? dlsym(bnd, "ABinderProcess_setThreadPoolMaxThreadCount") : NULL;
    void (*startPool)(void) = bnd ? dlsym(bnd, "ABinderProcess_startThreadPool") : NULL;
    if (!setMax || !startPool) { fprintf(stderr, "binder thread pool API unavailable\n"); return 1; }
    setMax(4);
    startPool();

    ACameraManager *mgr = ACameraManager_create();
    ACameraDevice_StateCallbacks dcb = { NULL, onDisconnected, onError };
    ACameraDevice *dev = NULL;
    CHECK(ACameraManager_openCamera(mgr, id, &dcb, &dev));

    AImageReader *reader = NULL;
    CHECKM(AImageReader_new(w, h, format, 4, &reader));
    ANativeWindow *win = NULL;
    CHECKM(AImageReader_getWindow(reader, &win));

    int preview = argc > 6;
    AImageReader *preader = NULL; ANativeWindow *pwin = NULL;
    if (preview) {
        CHECKM(AImageReader_new(1920, 1080, AIMAGE_FORMAT_YUV_420_888, 4, &preader));
        CHECKM(AImageReader_getWindow(preader, &pwin));
    }

    ACaptureSessionOutputContainer *outs; ACaptureSessionOutput *out, *pout; ACameraOutputTarget *tgt, *ptgt;
    CHECK(ACaptureSessionOutputContainer_create(&outs));
    CHECK(ACaptureSessionOutput_create(win, &out));
    CHECK(ACaptureSessionOutputContainer_add(outs, out));
    if (preview) {
        CHECK(ACaptureSessionOutput_create(pwin, &pout));
        CHECK(ACaptureSessionOutputContainer_add(outs, pout));
    }
    ACameraCaptureSession_stateCallbacks scb = { NULL, onSessClosed, onSessReady, onSessActive };
    ACameraCaptureSession *sess = NULL;
    CHECK(ACameraDevice_createCaptureSession(dev, outs, &scb, &sess));

    ACaptureRequest *req = NULL;
    CHECK(ACameraDevice_createCaptureRequest(dev, TEMPLATE_PREVIEW, &req));
    CHECK(ACameraOutputTarget_create(win, &tgt));
    CHECK(ACaptureRequest_addTarget(req, tgt));
    if (preview) {
        CHECK(ACameraOutputTarget_create(pwin, &ptgt));
        CHECK(ACaptureRequest_addTarget(req, ptgt));
    }
    ACameraCaptureSession_captureCallbacks ccb = { 0 };
    ccb.onCaptureFailed = onFailed;
    int seq = 0;
    CHECK(ACameraCaptureSession_setRepeatingRequest(sess, &ccb, 1, &req, &seq));

    int frames = 0, pframes = 0; AImage *img = NULL;
    int64_t t0 = 0, t1 = 0;
    for (int i = 0; i < 500; i++) {           // ~5 s: let AE/AWB converge, count delivered frames
        usleep(10000);
        AImage *n = NULL;
        while (AImageReader_acquireNextImage(reader, &n) == AMEDIA_OK) {
            int64_t ts; AImage_getTimestamp(n, &ts);
            if (frames == 5) t0 = ts;          // skip startup frames for the rate estimate
            t1 = ts;
            frames++;
            if (img) AImage_delete(img);
            img = n;
        }
        while (preview && AImageReader_acquireNextImage(preader, &n) == AMEDIA_OK) {
            pframes++;
            AImage_delete(n);
        }
    }
    ACameraCaptureSession_stopRepeating(sess);
    printf("frames_received=%d", frames);
    if (frames > 6) printf(" steady_fps=%.2f", (frames - 6) * 1e9 / (double)(t1 - t0));
    if (preview) printf(" preview_frames=%d", pframes);
    printf("\n");
    if (!img) { fprintf(stderr, "no frame delivered\n"); return 1; }
    if (yuv) { AImage_delete(img); return 0; }

    uint8_t *data; int len, stride; int32_t iw, ih, fmt; int64_t ts;
    AImage_getWidth(img, &iw); AImage_getHeight(img, &ih); AImage_getFormat(img, &fmt);
    AImage_getTimestamp(img, &ts);
    CHECKM(AImage_getPlaneData(img, 0, &data, &len));
    CHECKM(AImage_getPlaneRowStride(img, 0, &stride));
    printf("image %dx%d fmt=0x%x rowStride=%d len=%d ts=%lld\n", iw, ih, fmt, stride, len, (long long)ts);

    FILE *f = fopen(argv[4], "wb");
    double sum[4] = {0}; long cnt[4] = {0}; unsigned mn = 65535, mx = 0;
    for (int y = 0; y < ih; y++) {
        const uint16_t *row = (const uint16_t *)(data + (size_t)y * stride);
        fwrite(row, 2, iw, f);
        for (int x = 0; x < iw; x++) {
            unsigned v = row[x]; int c = ((y & 1) << 1) | (x & 1);
            sum[c] += v; cnt[c]++; if (v < mn) mn = v; if (v > mx) mx = v;
        }
    }
    fclose(f);
    printf("min=%u max=%u mean[cfa00,01,10,11]=%.1f %.1f %.1f %.1f\n", mn, mx,
           sum[0] / cnt[0], sum[1] / cnt[1], sum[2] / cnt[2], sum[3] / cnt[3]);

    AImage_delete(img);
    ACameraCaptureSession_close(sess);
    ACameraDevice_close(dev);
    AImageReader_delete(reader);
    ACameraManager_delete(mgr);
    return 0;
}
