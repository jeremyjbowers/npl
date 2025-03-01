import os

db_connex = {
    "dbname": os.environ.get("PROD_PGDBNAME"),
    "pgpass": os.environ.get("PROD_PGPASS"),
    "pguser": os.environ.get("PROD_PGUSER"),
    "pghost": os.environ.get("PROD_PGHOST"),
    "pgport": os.environ.get("PROD_PGPORT")
}

if __name__ == "__main__":
    missing_env_vars = []

    for var, env_var in db_connex.items():
        if not env_var:
            missing_env_vars.append(var)

    if len(missing_env_vars) > 0: 
        for env_var in missing_env_vars:
            print(f"$ENV is issing {env_var}")
    else:
        print(f"PGSSLMODE=require PGPASSWORD={db_connex['pgpass']} pg_dump -U {db_connex['pguser']} -h {db_connex['pghost']} -p {db_connex['pgport']} {db_connex['dbname']} > data/sql/{db_connex['dbname']}.sql")
        os.system(f"PGSSLMODE=require PGPASSWORD={db_connex['pgpass']} pg_dump -U {db_connex['pguser']} -h {db_connex['pghost']} -p {db_connex['pgport']} {db_connex['dbname']} > data/sql/{db_connex['dbname']}.sql")