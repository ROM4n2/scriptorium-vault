#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdatomic.h>

// ==============================================================================
// 📦 C11 Defensive Opaque Struct & Goto Cleanup Pattern
// ==============================================================================

#define SAFE_FREE(p) do { if (p) { free(p); (p) = NULL; } } while (0)

typedef struct net_session_s {
    int socket_fd;
    char* client_ip;
    atomic_int packet_count;
} net_session_t;

net_session_t* net_session_create(int fd, const char* ip) {
    if (!ip || fd < 0) return NULL;

    net_session_t* session = (net_session_t*)calloc(1, sizeof(net_session_t));
    if (!session) return NULL;

    session->socket_fd = fd;
    session->client_ip = (char*)malloc(64);
    if (!session->client_ip) {
        SAFE_FREE(session);
        return NULL;
    }

    snprintf(session->client_ip, 64, "%s", ip);
    atomic_init(&session->packet_count, 0);
    return session;
}

void net_session_destroy(net_session_t** session_ptr) {
    if (!session_ptr || !*session_ptr) return;

    net_session_t* s = *session_ptr;
    SAFE_FREE(s->client_ip);
    SAFE_FREE(*session_ptr);
}
