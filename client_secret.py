import os
GOOGLE_CLIENT_ID=os.environ['GOOGLE_CLIENT_ID']
GOOGLE_PROJECT_ID=os.environ['GOOGLE_PROJECT_ID']
GOOGLE_AUTH_URI=os.environ['GOOGLE_AUTH_URI']
GOOGLE_TOKEN_URI=os.environ['GOOGLE_TOKEN_URI']
GOOGLE_AUTH_PROVIDER=os.environ['GOOGLE_AUTH_PROVIDER']
GOOGLE_CLIENT_SECRET=os.environ['GOOGLE_CLIENT_SECRET']
REDIRECT_URL=os.environ['REDIRECT_URL']
client_secret = {"web":
                 {"client_id":GOOGLE_CLIENT_ID,
                  "project_id":GOOGLE_PROJECT_ID,
                  "auth_uri":GOOGLE_AUTH_URI,
                  "token_uri":GOOGLE_TOKEN_URI,
                  "auth_provider_x509_cert_url":GOOGLE_AUTH_PROVIDER
                  ,"client_secret":GOOGLE_CLIENT_SECRET,
                  "redirect_uris":[REDIRECT_URL]
                  }
                }


initial_html = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Document</title>
</head>
<body>
  
</body>
</html>"""
