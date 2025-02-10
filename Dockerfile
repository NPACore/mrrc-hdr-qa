# USAGE:
#  docker run -it  \
#    -v sim:/app/sim `# forward sim dir`\
#    -v .:/app `# put current app code into container` \
#    `# let these ports escape docker (http and websockets)` \
#    -p 8080:8080 -p 5000:5000  \
#    mrqart \
#    `# actually run server with arg specified settings` \
#    LOGLEVEL=DEBUG ./mrqart.py -p 8080 --watch sim 
#
# ISSUES:
# * docker on macOS w/fuse does not support inotify?
#   https://stackoverflow.com/questions/70117645/inotify-on-docker-mounted-volumes-mac-linux
# * inotify doesn't work in podman. 
#   https://github.com/containers/podman/issues/22343
#
from python:3.13-slim-bookworm as compiler
WORKDIR /app/
COPY ./requirements.txt /app/requirements.txt
# need make and gcc for numpy
RUN apt-get update && \
    apt-get install -y \
        build-essential \
        make  gcc && \
    pip install -Ur requirements.txt

# TODO(20250210): remove apt files in above
# TODO(20250210): use new 'from' line and copy python install files (image w/o make, gcc, etc)
# TODO(20250210): copy app code (maybe after reorg to module)
