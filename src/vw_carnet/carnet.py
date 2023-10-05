from bs4 import BeautifulSoup
from uuid import uuid4

import json5 as json
import pkce
import re
import requests
import time

VW_BASE_URL = 'https://b-h-s.spr.us00.p.con-veh.net'
VW_CLIENT_ID = '2dae49f6-830b-4180-9af9-59dd0d060916@apps_vw-dilab_com'
VW_IDENTITY_URL = 'https://identity.na.vwgroup.io'
VW_OAUTH_CALLBACK = 'car-net:///oauth-callback'

CAR_STATUS_EXP_SECONDS = 60
ACCT_STATUS_EXP_SECONDS = 3600

class CarNet:

    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.headers = {'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/117.0'}

        self.tokens = None
        self.acctStatus = None
        self.carStatus = None


    def setTokens(self, tokens):
        self.tokens = tokens
        self.tokens['expiration_date'] = time.time() + tokens['expires_in']


    def getTokens(self):
        if self.tokens is None:
            self.login()
        if self.isExpired(self.tokens):
            self.refreshTokens()
        return self.tokens


    def refreshTokens(self):
        if self.tokens is None:
            raise Exception('cannot refresh with null tokens')

        refreshTokensURL = '{}/oidc/v1/token'.format(VW_BASE_URL)
        refreshTokensR = self.session.post(refreshTokensURL, allow_redirects=True, params={
            'client_id': VW_CLIENT_ID,
            'code_verifier': self.verifier,
            'grant_type': 'refresh_token',
            'refresh_token': self.tokens['refresh_token'],
        },
        headers={
            'content-type': 'application/x-www-form-urlencoded'
        })
        self.setTokens(refreshTokensR.json())


    def isExpired(self, d):
        if d is None or time.time() > d['expiration_date']:
            return True
        else:
            return False

    def getCarStatus(self):
        if self.isExpired(self.carStatus) is True:
            self.carStatus = {}
            acctStatus = self.getAcctStatus()
            for vehicle in acctStatus['data']['vehicleEnrollmentStatus']:
                vehicleId = vehicle['vehicleId']

                tokens = self.getTokens()
                carStatURL = '{}/rvs/v1/vehicle/{}'.format(VW_BASE_URL, vehicleId)
                carStatR = self.session.get(carStatURL,
                    params={'idToken':tokens['id_token']},
                    headers={'Authorization': 'Bearer {}'.format(tokens['access_token'])}
                )
                self.carStatus[vehicleId] = carStatR.json()
            self.carStatus['expiration_date'] = time.time() + CAR_STATUS_EXP_SECONDS

        return { k:self.carStatus[k] for k in self.carStatus.keys() if k != 'expiration_date' }


    def getAcctStatus(self):
        if self.isExpired(self.acctStatus) is False:
            return self.acctStatus

        tokens = self.getTokens()
        acctStatURL = '{}/account/v1/enrollment/status'.format(VW_BASE_URL)
        acctStatR = self.session.get(acctStatURL,
            params={'idToken':tokens['id_token']},
            headers={'Authorization': 'Bearer {}'.format(tokens['access_token'])}
        )

        self.acctStatus = acctStatR.json()
        self.acctStatus['expiration_date'] = time.time() + ACCT_STATUS_EXP_SECONDS
        return self.acctStatus


    def login(self):
        if self.tokens is not None:
            return

        self.verifier = pkce.generate_code_verifier(length=128)
        ### by spec (https://www.rfc-editor.org/rfc/rfc7636) trailing '=' should
        ###   be omitted, but VW fails the spec :smh:
        challenge = pkce.get_code_challenge(self.verifier) + '='

        uuid = str(uuid4())
        authURL = '{}/oidc/v1/authorize'.format(VW_BASE_URL)
        authR = self.session.get(authURL, allow_redirects=True, params={
            'client_id': VW_CLIENT_ID,
            'code_challenge': challenge,
            'code_challenge_method': 'S256',
            'prompt': 'login',
            'redirect_uri': VW_OAUTH_CALLBACK,
            'response_type': 'code',
            'scope': 'openid',
            'state': uuid,
        })

        soup = BeautifulSoup(authR.text, features='lxml')
        action = self.getActionFromSoup(soup)
        params = self.getParamsFromSoup(soup)
        params['email'] = self.username

        emailURL = '{}{}'.format(VW_IDENTITY_URL, action)
        emailR = self.session.post(emailURL, allow_redirects=True, params=params)

        idk = self.getJsonFromEmailR(emailR)
        action = self.getActionFromIDK(idk, action)
        params = self.getParamsFromIDK(idk)
        params['password'] = self.password

        passURL = '{}{}'.format(VW_IDENTITY_URL, action)
        authCode = False

        passR = self.session.post(passURL, allow_redirects=False, params=params)
        while authCode is False:
            if passR.status_code == 302 or passR.status_code == 303:
                passURL = passR.headers['location']
                if passURL.startswith('car-net:/'):
                    authCode = self.getAuthCode(passURL)
                else:
                    passR = self.session.get(passURL, allow_redirects=False)
            else:
                raise Exception('unexpected status code={} in redirect chain when submitting password'.format(passR.status_code))

        authTokensURL = '{}/oidc/v1/token'.format(VW_BASE_URL)
        authTokensR = self.session.post(authTokensURL, allow_redirects=True, params={
            'client_id': VW_CLIENT_ID,
            'code': authCode,
            'code_verifier': self.verifier,
            'grant_type': 'authorization_code',
            'redirect_uri': VW_OAUTH_CALLBACK,
        },
        headers={
            'content-type': 'application/x-www-form-urlencoded'
        })

        self.setTokens(authTokensR.json())

    def getAuthCode(self, url):
        ### get all
        params = re.split(r'[?&]', url)
        for param in params:
            if param.startswith('code='):
                codeParts = re.split(r'=', param)
                if len(codeParts) == 2 and codeParts[0] == 'code':
                    return codeParts[1]
        raise Exception('could not coerce url={} into auth code'.format(url))


    def getParamsFromIDK(self, idk):
        return {
            '_csrf': idk['csrf_token'],
            'relayState': idk['templateModel']['relayState'],
            'hmac': idk['templateModel']['hmac'],
            'email': idk['templateModel']['emailPasswordForm']['email'],
        }


    def getActionFromIDK(self, idk, action):
        return re.sub(r'login\/[a-zA-Z0-9]*$', idk['templateModel']['postAction'], action)


    def getJsonFromEmailR(self, emailR):
        data = None
        parts = re.split(r'<script>|<\/script>', emailR.text)
        for part in parts:
            if "window._IDK = " in part:
                part = re.sub('.*window._IDK = ', '', part)
                return json.loads(part)
        raise Exception('could not get json from emailR')


    def getActionFromSoup(self, soup):
        action = None
        form = soup.find('form')
        action = form.get('action')
        return action


    def getParamsFromSoup(self, soup):
        params = {}
        form = soup.find('form')
        inputs = form.find_all('input', {'type': 'hidden'})
        for i in inputs:
            name = i['name']
            value = i['value']
            params[name] = value
        return params
