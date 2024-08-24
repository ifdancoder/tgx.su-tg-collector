USERNAME := $(shell whoami)

ifeq ($(USERNAME),root)
    USERNAME := $(shell sudo -u $(SUDO_USER) whoami)
endif

perm:
	sudo usermod -aG www-data $(USERNAME)
	sudo chown -R $(USERNAME):$(USERNAME) ./

down: 
	docker-compose down

up:
	docker-compose up -d

reup: down up

build:
	docker-compose build --build-arg USERNAME=$(USERNAME)

build-up: perm down build
	docker-compose up -d

rebuild-up: perm down build-up