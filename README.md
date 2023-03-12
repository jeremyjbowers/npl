# The National Pastime League

## basics
* install virtualenv
* install virtualenvwrapper
* install postgres (I use postgres.app) and the command-line tools

## next
### pull down the repo
```
git clone git@github.com:jeremyjbowers/npl.git
```
### set up your django env
```cd npl
mkvirtualenv npl
add2virtualenv .
add2virtualenv config
add2virtualenv npl
export DJANGO_SETTINGS_MODULE=config.dev.settings
```
### install requirements
```
pip install -r requirements.txt
```

### load initial data
```
createdb npl
psql npl < npl.sql
```

### run the server
```
django-admin runserver
```

You'll be able to see this at `http://127.0.0.1:8000`.

I recommend editing your `/etc/hosts` to add a line like this:
```
127.0.0.1   localhost.nationalpastime.org
```