# Use a imagem oficial do Python
FROM python:3.9-slim

# Define o fuso horário para São Paulo
ENV TZ=America/Sao_Paulo

# Instale as dependências do sistema operacional necessárias para definir o fuso horário
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Define o diretório de trabalho dentro do container
WORKDIR /app

# Copia os arquivos do projeto para o container
COPY . .

# Instala as dependências do projeto
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

# Expõe a porta 8000 para acessar o FastAPI
EXPOSE 8000

# Comando para rodar o FastAPI com Uvicorn
CMD ["uvicorn", "api_service:app", "--host", "0.0.0.0", "--port", "8000"]