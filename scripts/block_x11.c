/* LD_PRELOAD hook: block X11 port connections.
 * mpirun/orted probes X11 ports 6000-6063 during startup.
 * In AutoDL Docker containers, port 6007 is intercepted by Docker NAT
 * and forwarded to a VNC server that never responds to X11 protocol.
 *
 * Compile: gcc -shared -fPIC -o block_x11.so block_x11.c -ldl
 * Usage: LD_PRELOAD=./block_x11.so mpirun -np N vasp_std
 */
#define _GNU_SOURCE
#include <stddef.h>
#include <dlfcn.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <errno.h>
#include <arpa/inet.h>

typedef int (*connect_fn)(int, const struct sockaddr *, socklen_t);

int connect(int sockfd, const struct sockaddr *addr, socklen_t addrlen) {
    static connect_fn real_connect = NULL;
    if (!real_connect) {
        real_connect = (connect_fn)dlsym(RTLD_NEXT, "connect");
        if (!real_connect) {
            /* fallback: try the standard symbol */
            real_connect = (connect_fn)dlsym(RTLD_DEFAULT, "connect");
        }
    }

    /* Block X11 TCP ports (6000-6063) on loopback */
    if (addr->sa_family == AF_INET) {
        struct sockaddr_in *sin = (struct sockaddr_in *)addr;
        unsigned short port = ntohs(sin->sin_port);
        if (port >= 6000 && port <= 6063
            && sin->sin_addr.s_addr == htonl(INADDR_LOOPBACK)) {
            errno = ECONNREFUSED;
            return -1;
        }
    }

    return real_connect(sockfd, addr, addrlen);
}
