/* Regression for GHSA-6933-cjhr-5qg6. Uses the actual public native API. */
#include <nghttp2/nghttp2.h>
#include <stdio.h>
#include <string.h>

static int received;
static int terminate_on_frame(nghttp2_session *session,
                              const nghttp2_frame *frame, void *user_data) {
  (void)user_data;
  ++received;
  if (frame->hd.type == NGHTTP2_ALTSVC)
    return nghttp2_session_terminate_session(session, NGHTTP2_NO_ERROR);
  return 0;
}

int main(void) {
  nghttp2_session *session;
  nghttp2_session_callbacks *callbacks;
  nghttp2_option *option;
  /* Initial SETTINGS, valid ALTSVC (origin=x), then SETTINGS which must be ignored. */
  static const unsigned char input[] = {
    0,0,0, NGHTTP2_SETTINGS,0, 0,0,0,0,
    0,0,4, NGHTTP2_ALTSVC,0, 0,0,0,0, 0,1,'x','y',
    0,0,0, NGHTTP2_SETTINGS,0, 0,0,0,0
  };
  static const unsigned char malformed[] = {
    0,0,1, NGHTTP2_PING,0, 0,0,0,0, 0
  };
  int result = 1;
  if (nghttp2_session_callbacks_new(&callbacks) || nghttp2_option_new(&option))
    return 2;
  nghttp2_session_callbacks_set_on_frame_recv_callback(callbacks, terminate_on_frame);
  nghttp2_option_set_builtin_recv_extension_type(option, NGHTTP2_ALTSVC);
  if (nghttp2_session_client_new2(&session, callbacks, NULL, option)) return 2;
  if (nghttp2_session_mem_recv2(session, input, sizeof(input)) != sizeof(input))
    fprintf(stderr, "Failed to consume input\n");
  else if (received != 2)
    fprintf(stderr, "Reading continued after termination: callbacks=%d\n", received);
  else if (nghttp2_session_mem_recv2(session, malformed, sizeof(malformed)) != sizeof(malformed)
           || received != 2)
    fprintf(stderr, "Malformed input was not ignored after termination\n");
  else {
    puts("nghttp2 stop-reading regression: passed (2 callbacks; trailing frames ignored)");
    result = 0;
  }
  nghttp2_session_del(session);
  nghttp2_option_del(option);
  nghttp2_session_callbacks_del(callbacks);
  return result;
}
