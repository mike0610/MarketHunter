#!/bin/sh
# Certbot deploy hook. Reload Nginx only when this isolated scanner cert renews.
set -eu
case " ${RENEWED_DOMAINS:-} " in
  *" 149-56-45-39.sslip.io "*) /usr/sbin/nginx -t && /bin/systemctl reload nginx ;;
  *) exit 0 ;;
esac
