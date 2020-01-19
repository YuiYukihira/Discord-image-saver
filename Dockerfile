FROM alpine:latest
LABEL maintainer="Yui Yukihira <yuiyukihira@pm.me>"
EXPOSE 8080
COPY docker/install.sh /install.sh
COPY requirements.txt /requirements.txt
RUN sh /install.sh
COPY src /src
ENTRYPOINT ["python3.7"]
CMD ["/src/index.py"]
