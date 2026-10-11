# The box the AI's own Python runs in (SPEC §7.3, run_python): Python 3.12, numpy and Pillow.
# Build: docker build -t kairo-python:1 src/kairo_pdf_json/tools/sandbox
FROM python:3.12.11-slim-bookworm
RUN pip install --no-cache-dir numpy==2.2.6 pillow==11.3.0
RUN useradd --uid 1000 --no-create-home runner
USER runner
WORKDIR /work
