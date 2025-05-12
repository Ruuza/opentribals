# OpenTribals
Open sourced Browser RTS game inspired by Tribal Wars.

This project is an API written in FastAPI. There is no frontend yet.

## How to Run the Project Locally

This manual provides instructions on how to set up and run the project locally.

The source code for this project is available at: <https://github.com/ruuza/opentribals>

### Steps to Run the Project
1.  Download or clone the repository from the provided URL.
2.  Navigate to the project's root directory.
3.  Copy the `.env.template` file to a new file named `.env`.
4.  Open the `.env` file and fill in the required values:
    *   `SECRET_KEY`: Generate a strong secret key.
    *   `FIRST_SUPERUSER_PASSWORD`: Set the password for the initial superuser.
    *   `POSTGRES_PASSWORD`: Set the password for the PostgreSQL database.
5.  Run the following command in your terminal to build and start the Docker containers:
    ````
    docker compose up -d --build
    ````
6.  Once the containers are running, open your web browser and navigate to <http://localhost:8021/docs> to access the API documentation.
7.  To interact with the game:
    *   Authenticate by logging in with the superuser credentials (username is `admin@example.com` by default, or as set in `.env`, and the password is `FIRST_SUPERUSER_PASSWORD` you set).
    *   Join the game world and obtain your first village by making a POST request to the `/api/v1/world/join` endpoint.