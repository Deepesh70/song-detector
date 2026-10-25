# Cloud API & Integration Reference

HearThis communicates directly with commercial music recognition cloud providers over TLS without an intermediary backend server. This document details the request construction, cryptographic signature generation, and response parsing for each supported provider, as well as the local client configuration schema.

---

## 1. ACRCloud Identify API (Default Provider)

ACRCloud provides low-latency fingerprint matching against a catalog of over 100 million tracks. Requests require HMAC-SHA1 cryptographic signing generated with native Windows BCrypt APIs.

- **Protocol**: HTTPS POST
- **Host**: Configured by user (e.g., `identify-eu-west-1.acrcloud.com` or `identify-us-west-2.acrcloud.com`)
- **Endpoint**: `/v1/identify`
- **Content-Type**: `multipart/form-data; boundary=----HearThisBoundary<RandomToken>`

### Request Multipart Form Fields

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `sample` | Binary | 16-bit linear PCM WAV audio buffer (44-byte RIFF header included) |
| `sample_bytes` | String | Decimal length of audio buffer in bytes (e.g. `960044` for 10s mono at 48 kHz) |
| `access_key` | String | ACRCloud project Access Key |
| `data_type` | String | Constant string: `audio` |
| `signature_version` | String | Constant string: `1` |
| `signature` | String | Base64-encoded HMAC-SHA1 cryptographic digest |
| `timestamp` | String | Current Unix epoch timestamp in UTC seconds (e.g. `1774312891`) |

### HMAC-SHA1 Signature Algorithm

1. Formulate the canonical String-to-Sign with strict newline delimiters:
   ```
   POST\n/v1/identify\n<access_key>\naudio\n1\n<timestamp>
   ```
2. Compute the HMAC-SHA1 digest using the project's `access_secret` as the secret key:
   - Evaluated via Windows `bcrypt.dll` (`BCRYPT_SHA1_ALGORITHM` with `BCRYPT_ALG_HANDLE_HMAC_FLAG`).
3. Encode the resulting 20-byte binary digest into standard Base64:
   - Evaluated via Windows `crypt32.dll` (`CryptBinaryToStringA`).

### Expected Response Format (JSON)

#### Successful Match (`status.code == 0`)
```json
{
  "status": {
    "code": 0,
    "msg": "Success",
    "version": "1.0"
  },
  "metadata": {
    "music": [
      {
        "title": "Midnight City",
        "artists": [
          { "name": "M83" }
        ],
        "album": {
          "name": "Hurry Up, We're Dreaming"
        },
        "external_metadata": {
          "spotify": {
            "track": { "id": "6GyFP1nfCDB8Jy62v8Aq4q" }
          },
          "youtube": {
            "vid": "dX3k_QDnzHE"
          }
        }
      }
    ]
  }
}
```

#### No Match Found (`status.code == 1001`)
```json
{
  "status": {
    "code": 1001,
    "msg": "No result",
    "version": "1.0"
  }
}
```

---

## 2. AudD Music Recognition API (Secondary Provider)

AudD provides song identification with simple token-based authentication.

- **Protocol**: HTTPS POST
- **Host**: `api.audd.io`
- **Endpoint**: `/`
- **Content-Type**: `multipart/form-data; boundary=----HearThisBoundary<RandomToken>`

### Request Multipart Form Fields

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `file` | Binary | 16-bit linear PCM WAV audio buffer |
| `api_token` | String | AudD user API token |
| `return` | String | Comma-delimited list of extra metadata providers: `timecode,apple_music,spotify` |

### Expected Response Format (JSON)

#### Successful Match (`status == "success"` and `result != null`)
```json
{
  "status": "success",
  "result": {
    "title": "Starboy",
    "artist": "The Weeknd ft. Daft Punk",
    "album": "Starboy",
    "release_date": "2016-11-25",
    "song_link": "https://lis.tn/Starboy"
  }
}
```

#### No Match Found
```json
{
  "status": "success",
  "result": null
}
```

---

## 3. Local Client Configuration Schema

HearThis automatically persists user credentials and UI state in:
```
%APPDATA%\HearThis\config.txt
```
*(Note: If a legacy config file exists at `%APPDATA%\SongDetector\native_config.txt`, it is automatically migrated upon startup.)*

### File Format Specification
The configuration is stored as newline-separated UTF-8 key-value pairs (`key=value`):

```ini
provider=acrcloud
acr_host=identify-eu-west-1.acrcloud.com
acr_key=ab12cd34ef567890
acr_secret=1a2b3c4d5e6f7g8h9i0j
audd_token=
duration=10
audio_source=speakers
```

### Configuration Keys Reference

| Key | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `provider` | `acrcloud` \| `audd` | `acrcloud` | Active cloud provider selected by the user |
| `acr_host` | String | `""` | ACRCloud project endpoint host |
| `acr_key` | String | `""` | ACRCloud access key |
| `acr_secret` | String | `""` | ACRCloud access secret |
| `audd_token` | String | `""` | AudD API token |
| `duration` | Integer (`5` \| `10`) | `10` | Audio capture duration in seconds |
| `audio_source` | `speakers` \| `mic` | `speakers` | Selected input: internal loopback (`speakers`) or microphone (`mic`) |
