#define _POSIX_C_SOURCE 200809L
/* Typed ABI boundary. All curl option values come from the pinned headers. */
#include <curl/curl.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

typedef size_t (*ci_writer)(const unsigned char *, size_t, void *);
typedef struct {
  CURL *easy;
  struct curl_slist *headers;
  ci_writer body;
  ci_writer header;
  void *userdata;
  char error[CURL_ERROR_SIZE];
} ci_handle;

static size_t body_cb(char *ptr, size_t size, size_t count, void *ctx) {
  ci_handle *h = ctx;
  if(size && count > SIZE_MAX / size) return 0;
  return h->body((const unsigned char *)ptr, size * count, h->userdata);
}

static size_t header_cb(char *ptr, size_t size, size_t count, void *ctx) {
  ci_handle *h = ctx;
  if(size && count > SIZE_MAX / size) return 0;
  return h->header((const unsigned char *)ptr, size * count, h->userdata);
}

int ci_global_init(void) { return (int)curl_global_init(CURL_GLOBAL_DEFAULT); }
const char *ci_version(void) { return curl_version(); }

void ci_free(ci_handle *h) {
  if(!h) return;
  curl_easy_cleanup(h->easy);
  curl_slist_free_all(h->headers);
  free(h);
}

ci_handle *ci_new(ci_writer body, ci_writer header, void *userdata) {
  ci_handle *h = calloc(1, sizeof(*h));
  if(!h) return NULL;
  h->easy = curl_easy_init();
  if(!h->easy) { free(h); return NULL; }
  h->body = body;
  h->header = header;
  h->userdata = userdata;
#define INIT(opt, val) do { if(curl_easy_setopt(h->easy, opt, val)) { ci_free(h); return NULL; } } while(0)
  INIT(CURLOPT_ERRORBUFFER, h->error);
  INIT(CURLOPT_NOSIGNAL, 1L);
  INIT(CURLOPT_NOPROGRESS, 1L);
  INIT(CURLOPT_MAXREDIRS, 50L);
  INIT(CURLOPT_PROTOCOLS_STR, "http,https");
  INIT(CURLOPT_REDIR_PROTOCOLS_STR, "http,https");
  INIT(CURLOPT_WRITEFUNCTION, body_cb);
  INIT(CURLOPT_WRITEDATA, h);
  INIT(CURLOPT_HEADERFUNCTION, header_cb);
  INIT(CURLOPT_HEADERDATA, h);
#undef INIT
  return h;
}

int ci_string(ci_handle *h, const char *name, const char *value) {
#define STR(n, opt) if(!strcmp(name, n)) return (int)curl_easy_setopt(h->easy, opt, value)
  STR("url", CURLOPT_URL);
  STR("method", CURLOPT_CUSTOMREQUEST);
  STR("impersonate", CURLOPT_IMPERSONATE);
  STR("user_agent", CURLOPT_USERAGENT);
  STR("referer", CURLOPT_REFERER);
  STR("user", CURLOPT_USERPWD);
  STR("proxy", CURLOPT_PROXY);
  STR("proxy_user", CURLOPT_PROXYUSERPWD);
  STR("no_proxy", CURLOPT_NOPROXY);
  STR("ca_cert", CURLOPT_CAINFO);
  STR("ca_path", CURLOPT_CAPATH);
  STR("encoding", CURLOPT_ACCEPT_ENCODING);
  STR("cookie", CURLOPT_COOKIE);
  STR("cookie_file", CURLOPT_COOKIEFILE);
  STR("cookie_jar", CURLOPT_COOKIEJAR);
#undef STR
  return CURLE_UNKNOWN_OPTION;
}

int ci_long(ci_handle *h, const char *name, long value) {
#define LONG(n, opt) if(!strcmp(name, n)) return (int)curl_easy_setopt(h->easy, opt, value)
  LONG("follow", CURLOPT_FOLLOWLOCATION);
  LONG("auto_referer", CURLOPT_AUTOREFERER);
  LONG("max_redirects", CURLOPT_MAXREDIRS);
  LONG("include", CURLOPT_HEADER);
  LONG("head", CURLOPT_NOBODY);
  LONG("get", CURLOPT_HTTPGET);
  LONG("fail", CURLOPT_FAILONERROR);
  LONG("verbose", CURLOPT_VERBOSE);
  LONG("timeout_ms", CURLOPT_TIMEOUT_MS);
  LONG("connect_timeout_ms", CURLOPT_CONNECTTIMEOUT_MS);
  LONG("verify_peer", CURLOPT_SSL_VERIFYPEER);
  LONG("verify_host", CURLOPT_SSL_VERIFYHOST);
  LONG("decode", CURLOPT_HTTP_CONTENT_DECODING);
#undef LONG
  if(!strcmp(name, "http_version")) {
    long versions[] = {CURL_HTTP_VERSION_1_0, CURL_HTTP_VERSION_1_1,
                       CURL_HTTP_VERSION_2_0, CURL_HTTP_VERSION_3, CURL_HTTP_VERSION_3ONLY};
    if(value < 0 || value > 4) return CURLE_BAD_FUNCTION_ARGUMENT;
    return (int)curl_easy_setopt(h->easy, CURLOPT_HTTP_VERSION, versions[value]);
  }
  return CURLE_UNKNOWN_OPTION;
}

int ci_header(ci_handle *h, const char *value) {
  struct curl_slist *next = curl_slist_append(h->headers, value);
  if(!next) return CURLE_OUT_OF_MEMORY;
  h->headers = next;
  return CURLE_OK;
}

int ci_body(ci_handle *h, const unsigned char *data, size_t len) {
  if(len > INT64_MAX) return CURLE_BAD_FUNCTION_ARGUMENT;
  CURLcode rc = curl_easy_setopt(h->easy, CURLOPT_POSTFIELDSIZE_LARGE, (curl_off_t)len);
  if(rc) return (int)rc;
  return (int)curl_easy_setopt(h->easy, CURLOPT_COPYPOSTFIELDS, (const char *)data);
}

int ci_perform(ci_handle *h) {
  CURLcode rc = curl_easy_setopt(h->easy, CURLOPT_HTTPHEADER, h->headers);
  return rc ? (int)rc : (int)curl_easy_perform(h->easy);
}

const char *ci_error(ci_handle *h, int code) {
  return h->error[0] ? h->error : curl_easy_strerror((CURLcode)code);
}

long ci_info_long(ci_handle *h, const char *name) {
  long value = 0;
  if(!strcmp(name, "http_code")) curl_easy_getinfo(h->easy, CURLINFO_RESPONSE_CODE, &value);
  else if(!strcmp(name, "num_redirects")) curl_easy_getinfo(h->easy, CURLINFO_REDIRECT_COUNT, &value);
  else if(!strcmp(name, "http_version")) curl_easy_getinfo(h->easy, CURLINFO_HTTP_VERSION, &value);
  return value;
}

const char *ci_info_string(ci_handle *h, const char *name) {
  char *value = NULL;
  if(!strcmp(name, "url_effective")) curl_easy_getinfo(h->easy, CURLINFO_EFFECTIVE_URL, &value);
  else if(!strcmp(name, "content_type")) curl_easy_getinfo(h->easy, CURLINFO_CONTENT_TYPE, &value);
  return value ? value : "";
}

double ci_total_time(ci_handle *h) {
  double value = 0;
  curl_easy_getinfo(h->easy, CURLINFO_TOTAL_TIME, &value);
  return value;
}

/* Filename timestamp in the process's local timezone (usually UTC in Docker). */
int ci_local_timestamp(char *buffer, size_t capacity) {
  time_t now = time(NULL);
  struct tm local;
  if(now == (time_t)-1 || !localtime_r(&now, &local)) return 0;
  return strftime(buffer, capacity, "%Y-%m-%d_%H-%M-%S", &local) != 0;
}

/* Only validated host/path bytes may be used in an export filename. */
int ci_url_host_path(const char *url, char *buffer, size_t capacity) {
  CURLU *parsed = curl_url();
  char *host = NULL, *path = NULL;
  int ok = 0;
  if(!capacity) { curl_url_cleanup(parsed); return 0; }
  buffer[0] = '\0';
  if(parsed &&
     !curl_url_set(parsed, CURLUPART_URL, url, CURLU_GUESS_SCHEME | CURLU_PATH_AS_IS) &&
     !curl_url_get(parsed, CURLUPART_HOST, &host, 0) &&
     !curl_url_get(parsed, CURLUPART_PATH, &path, 0)) {
    const char *parts[] = {host, path};
    size_t used = 0;
    for(size_t i = 0; i < 2; i++)
      for(const char *p = parts[i]; *p && used + 1 < capacity; p++)
        buffer[used++] = *p;
    buffer[used] = '\0';
    ok = 1;
  }
  curl_free(host);
  curl_free(path);
  curl_url_cleanup(parsed);
  return ok;
}
