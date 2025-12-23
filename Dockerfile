FROM python:3.11-alpine

# set work directory
WORKDIR /app

# set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# OS deps
RUN apk add --no-cache \
    ffmpeg \
    bash \
    build-base \
    libffi-dev \
    openssl-dev

RUN pip install --upgrade pip
COPY ./requirements.txt /app
RUN pip install -r requirements.txt

# copy project
COPY . /app

EXPOSE 8000



# Make scripts executable
RUN chmod +x start.sh start-dev.sh


CMD ["./start.sh"]
