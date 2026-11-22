# The scan image: Kali rolling plus a chosen set of command-line tools, and the scanner (lambdakali-scan) with boto3.
# CodeBuild runs one build per scanner on it; the buildspec's only command is lambdakali-scan.
# Keep TOOLS (the module variable, passed to the Lambda) in step with what APT_TOOLS installs here: the Lambda only
# lets a task use a tool on that list, and a task's tool must be on PATH in this image or the task ends in error.
FROM kalilinux/kali-rolling:latest

# a curated set: fast, well-known, non-interactive scanners. Add more by extending this list and TOOLS together.
ENV APT_TOOLS="nmap nikto whatweb wafw00f dnsutils dnsrecon sslscan testssl.sh nuclei whatweb sqlmap gobuster ffuf curl wget"
RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      python3 python3-boto3 ca-certificates $APT_TOOLS \
 && rm -rf /var/lib/apt/lists/* \
 && mkdir -p /work

COPY scan.py /usr/local/bin/lambdakali-scan
RUN chmod 755 /usr/local/bin/lambdakali-scan
WORKDIR /work
