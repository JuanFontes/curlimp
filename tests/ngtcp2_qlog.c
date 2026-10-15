/* Regression for CVE-2026-40170, exercised with AddressSanitizer. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "ngtcp2_qlog.h"

static void emit(void *user_data, uint32_t flags, const void *data, size_t length) {
  (void)user_data;
  (void)flags;
  if (fwrite(data, 1, length, stdout) != length) {
    _Exit(1);
  }
}

int main(void) {
  ngtcp2_transport_params params;
  ngtcp2_qlog qlog;
  uint8_t cid[NGTCP2_MAX_CIDLEN];
  const uint64_t max_varint = (UINT64_C(1) << 62) - 1;
  memset(cid, 0xab, sizeof(cid));
  ngtcp2_transport_params_default(&params);
  ngtcp2_cid_init(&params.initial_scid, cid, sizeof(cid));
  ngtcp2_cid_init(&params.original_dcid, cid, sizeof(cid));
  ngtcp2_cid_init(&params.retry_scid, cid, sizeof(cid));
  ngtcp2_cid_init(&params.preferred_addr.cid, cid, sizeof(cid));
  memset(params.stateless_reset_token, 0xcd, sizeof(params.stateless_reset_token));
  memset(params.preferred_addr.stateless_reset_token, 0xef,
         sizeof(params.preferred_addr.stateless_reset_token));
  params.preferred_addr.ipv4_present = 1;
  params.preferred_addr.ipv6_present = 1;
  params.preferred_addr.ipv4.sin_port = 0xffff;
  params.preferred_addr.ipv6.sin6_port = 0xffff;
  memset(&params.preferred_addr.ipv4.sin_addr, 0xff,
         sizeof(params.preferred_addr.ipv4.sin_addr));
  memset(&params.preferred_addr.ipv6.sin6_addr, 0xff,
         sizeof(params.preferred_addr.ipv6.sin6_addr));
  params.max_idle_timeout = UINT64_MAX;
  params.max_udp_payload_size = 65527;
  params.ack_delay_exponent = 20;
  params.max_ack_delay = 16383 * NGTCP2_MILLISECONDS;
  params.active_connection_id_limit = max_varint;
  params.initial_max_data = max_varint;
  params.initial_max_stream_data_bidi_local = max_varint;
  params.initial_max_stream_data_bidi_remote = max_varint;
  params.initial_max_stream_data_uni = max_varint;
  params.initial_max_streams_bidi = UINT64_C(1) << 60;
  params.initial_max_streams_uni = UINT64_C(1) << 60;
  params.max_datagram_frame_size = max_varint;
  params.disable_active_migration = 1;
  params.grease_quic_bit = 1;

  /* Include and omit every optional field, for both endpoints and directions. */
  for (int optional = 0; optional <= 1; ++optional) {
    params.retry_scid_present = optional;
    params.stateless_reset_token_present = optional;
    params.preferred_addr_present = optional;
    for (int server = 0; server <= 1; ++server) {
      for (int remote = 0; remote <= 1; ++remote) {
        ngtcp2_qlog_init(&qlog, emit, 0, NULL);
        qlog.last_ts = UINT64_MAX;
        ngtcp2_qlog_parameters_set_transport_params(
          &qlog, &params, server,
          remote ? NGTCP2_QLOG_SIDE_REMOTE : NGTCP2_QLOG_SIDE_LOCAL);
      }
    }
  }
  ngtcp2_qlog_init(&qlog, NULL, 0, NULL);
  ngtcp2_qlog_parameters_set_transport_params(
    &qlog, &params, 0, NGTCP2_QLOG_SIDE_REMOTE);
  return 0;
}
