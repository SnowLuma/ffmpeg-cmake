#include <stdio.h>
#include <libavcodec/avcodec.h>
#include <libavformat/avformat.h>
#include <libavfilter/avfilter.h>

int main(void)
{
    void *iterator = NULL;
    const AVCodec *codec;
    unsigned count = 0;
    unsigned filters = 0;
    while ((codec = av_codec_iterate(&iterator)))
        count++;
    iterator = NULL;
    while (av_filter_iterate(&iterator))
        filters++;
    printf("avcodec=%u avformat=%u codecs=%u filters=%u\n",
           avcodec_version(), avformat_version(), count, filters);
    return avcodec_version() == 0 || avformat_version() == 0;
}
