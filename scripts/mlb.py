import requests
from bs4 import BeautifulSoup
import ujson as json
import csv
from nameparser import HumanName
import time
import os

players = []

# with open('data/international_with_birthdates.json', 'r') as readfile:
#     players = json.loads(readfile.read())

BASE_URL = "https://yvo49oxzy7-dsn.algolia.net/1/indexes/*/queries?x-algolia-api-key=2305f7af47eda36d30e1fa05f9986e56&x-algolia-application-id=YVO49OXZY7"

players = [
    "Luis Serna",
    "Nathan Flewelling",
    "Jake Mangum",
    "Jeremy Pilon",
    "Devereaux Harrison",
    "Eddie Micheletti",
    "Carson Pierce",
    "Jackson Wentworth",
    "Nolan Perry",
    "Tyler Schweitzer",
    "Casey Saucke",
    "Ronny Hernandez",
    "Nick McLain",
    "Luis Reyes",
    "Adisyn Coffey",
    "Ryan Webb",
    "Cameron Sullivan",
    "Nick Enright",
    "Trei Cruz",
    "Thomas Bruss",
    "Seth Stephenson",
    "Zack Lee",
    "Tyson Guerrero",
    "Eric Cerantola",
    "Hyungchan Um",
    "Hunter Patteson",
    "Logan Martin",
    "Yunior Marte",
    "Beck Way",
    "Adrian Bohorquez",
    "Jose Olivares",
    "Cesar Lares",
    "Khadim Diaw",
    "Ty Langenberg",
    "Carson McCusker",
    "Noah Murdock",
    "Blake Beers",
    "Jackson Finley",
    "Dylan Fien",
    "Kyle Robinson",
    "Sam Stuhr",
    "Carlos Pacheco",
    "Bryce Mayer",
    "Ryan Verdugo",
    "Pascanel Ferreras",
    "Alimber Santa",
    "Juan Bello",
    "Dioris De La Rosa",
    "Rio Foster",
    "David Calabrese",
    "David Mershon",
    "Anthony Scull",
    "Samy Natera",
    "Joe Redfield",
    "Josh Hood",
    "Will Riley",
    "Brock Moore",
    "Victor Labrada",
    "Devin Fitz-Gerald",
    "Bryan Magdaleno",
    "Hayden Harris",
    "Ian Mejia",
    "Luke Waddell",
    "Eric Hartman",
    "Jacob Shafer",
    "Owen Hackman",
    "Dale Stanavich",
    "Ryan Ignoffo",
    "Evan Fitterer",
    "Eliazar Dishmey",
    "Wilfredo Lara",
    "Emmett Olson",
    "Josh White",
    "Grant Shepardson",
    "Felipe De La Cruz",
    "Ryan Lambert",
    "Ethan Lanthier",
    "Luis Moreno",
    "Marcus Morgan",
    "Caleb Ricketts",
    "Keaton Anthony",
    "Juan Amarante",
    "Kevin Made",
    "Marquis Grissom",
    "Yoel Tejada",
    "Jackson Kent",
    "Tyler Schoff",
    "Nick Peoples",
    "Sam Petersen",
    "Eli Lovich",
    "Daniel Avitiia",
    "JP Wheat",
    "Frankie Scalzo",
    "Kenyi Perez",
    "Andy Garriola",
    "Ariel Armas",
    "Yerlin Confidan",
    "Tristan Smith",
    "Luke Hayden",
    "Juan Ortuno",
    "Yorman Galindez",
    "Wande Torres",
    "Wes Clarke",
    "Nick Cimillo",
    "Brandon Bidois",
    "Sammy Siani",
    "Shawn Ross",
    "Jaden Woods",
    "Braden Davis",
    "Josh Kross",
    "Joshua Baez",
    "Bryan Torres",
    "Joseph King",
    "Jose Cabrera",
    "Ruben Santana",
    "Jacob Steinmetz",
    "Kenny Castillo",
    "Junior Ciprian",
    "Marcos Herrera",
    "Braylen Wimmer",
    "Lebarron Johnson",
    "Roynier Hernandez",
    "Zach Agnos",
    "Patrick Copen",
    "Logan Wagner",
    "Wyatt Crowell",
    "David Morgan",
    "Carson Montgomery",
    "Garrett Hawkins",
    "Cole Paplham",
    "Jayvien Sandridge",
    "Lamar King",
    "Gerelmi Maldonado",
    "Braxton Roxby",
    "Nate Furman",
    "Drake George",
    "Jakob Christian",
    "Spencer Miles",
    "Nick Sinacola",
    "Santiago Camacho",
    "Justin Gonzales",
    "Adriander Mejia",
    "Jeury Espinal"
]

for p in players:
    name = p
    data = {}

    data["requests"] = [
        {"indexName":"mlb-players","params":f"query={name}"},
    ]

    headers = {}
    headers['Accept'] = "*/*"
    headers['Accept-Encoding'] = "gzip, deflate, br"
    headers['Accept-Language'] = "en-US,en;q=0.9"
    headers['Connection'] = "keep-alive"
    headers['Content-Length'] = "603"
    headers['Host'] = "yvo49oxzy7-dsn.algolia.net"
    headers['Origin'] = "https://www.mlb.com"
    headers['Sec-Fetch-Dest'] = "empty"
    headers['Sec-Fetch-Mode'] = "cors"
    headers['Sec-Fetch-Site'] = "cross-site"
    headers['User-Agent'] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36 Edg/109.0.1518.70"
    headers['content-type'] = "application/x-www-form-urlencoded"
    headers['sec-ch-ua'] = '"Not_A Brand";v="99", "Microsoft Edge";v="109", "Chromium";v="109"'
    headers['sec-ch-ua-mobile'] = "?0"
    headers['sec-ch-ua-platform'] = '"macOS"'

    r = requests.post(BASE_URL, headers=headers, data=json.dumps(data))

    results = r.json()['results']
    mlb_id = ""
    if len(results[0]['hits']) > 0:
        mlb_id = results[0]['hits'][0]['url'].split('player/')[1].replace('/', '')

    print(f"{p},{mlb_id}")

    time.sleep(0.5)