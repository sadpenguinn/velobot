FROM python:3.7

ADD main.py /
ADD constants.py /
ADD requirements.txt /

RUN pip install -r /requirements.txt

CMD [ "python3.7", "/main.py" ]
