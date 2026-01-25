
# Objective

mapping the wikimedia api

[Tutorial to get started](https://api.wikimedia.org/wiki/Getting_started_with_Wikimedia_APIs#Python)


1) Create a Wikimedia Account
2) Create a personal API token
3) Hello world

```python
# Python 3
# Get today's featured article from English Wikipedia

import datetime
import requests

today = datetime.datetime.now()
date = today.strftime('%Y/%m/%d')

url = 'https://api.wikimedia.org/feed/v1/wikipedia/en/featured/' + date

headers = {
  'Authorization': 'Bearer YOUR_ACCESS_TOKEN',
  'User-Agent': 'YOUR_APP_NAME (YOUR_EMAIL_OR_CONTACT_PAGE)'
}

response = requests.get(url, headers=headers)
data = response.json()
print(data)

```


### Rate limits

[Rate Limits](https://api.wikimedia.org/wiki/Rate_limits)

Rate limits restrict API calls to a set number of requests per hour based on the type of request. A 429 response code indicates that the applicable rate limit has been exceeded.

These limits only apply to APIs with api.wikimedia.org as the base URL. Rate limits may vary depending on the API; see the API catalog for the rate limits applicable to each API. For higher rate limits, check out Wikimedia Enterprise.

Anonymous requests
* API requests without an access token are limited to 500 requests per hour per IP address.

Personal requests
* API requests authenticated using a personal API token are limited to 5,000 requests per hour.