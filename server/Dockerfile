FROM python:3.7

RUN pip install websockets
RUN pip install pymongo

WORKDIR /server

COPY . .

EXPOSE 6789

CMD ["python", "server.py"]