# The scan image: Kali rolling with a chosen tier of tools, the AWS CLI, and the scanner (lambdakali-scan) with boto3.
# CodeBuild runs one build per scanner on it; the buildspec's only command is lambdakali-scan, which then runs the
# commands you type in the console with `bash -lc`. The module builds one image per tier (slim, common, ...) and the
# console picks which to start, like the instance size.
#
#   KALI_TIER=slim    a dozen common tools: nmap, nikto, sqlmap, nuclei, gobuster, ffuf, sslscan, dnsrecon, john,
#                     hydra (small image, ~1 min to start)
#   KALI_TIER=common  four category metapackages: information-gathering, web, vulnerability, passwords (~80% of the
#                     common pentest tools; ~2-3 GB, a few minutes to start)
#   KALI_TIER=full    kali-linux-headless: the whole standard command-line toolset incl. metasploit (~5-8 GB)
#
# Any tool not in the tier installs on demand (root shell, apt, network): apt-get update && apt-get install -y <pkg>.
FROM kalilinux/kali-rolling:latest
ARG KALI_TIER=common

ENV SLIM_TOOLS="nmap nikto whatweb wafw00f dnsutils dnsrecon sslscan testssl.sh nuclei sqlmap gobuster ffuf john hydra"
ENV COMMON_SETS="kali-tools-information-gathering kali-tools-web kali-tools-vulnerability kali-tools-passwords"
# base: always; then the tier's packages. The metapackages rely on recommended packages, so they are installed
# without --no-install-recommends; the slim set is kept lean with it.
RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      bash python3 python3-boto3 ca-certificates curl wget awscli \
 && if [ "$KALI_TIER" = "slim" ]; then \
      DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends $SLIM_TOOLS; \
    elif [ "$KALI_TIER" = "full" ]; then \
      DEBIAN_FRONTEND=noninteractive apt-get install -y kali-linux-headless; \
    else \
      DEBIAN_FRONTEND=noninteractive apt-get install -y $COMMON_SETS; \
    fi \
 && rm -rf /var/lib/apt/lists/* \
 && mkdir -p /work

COPY scan.py /usr/local/bin/lambdakali-scan
RUN chmod 755 /usr/local/bin/lambdakali-scan
WORKDIR /work
