# API Reference

## Base URL
Development: `http://127.0.0.1:8000`

---

## Endpoints

### 1. Identify Track via Local Landmark Hashes

Executes fast inverted-index lookup against the local catalog using client-extracted landmark hashes.

- **Method**: `POST`
- **Path**: `/v1/recognize`
- **Content-Type**: `application/json`

#### Request Body
```json
{
  "hashes": [
    [-142081920, 12],
    [89102341, 15],
    [210491029, 21]
  ]
}
```
- `hashes`: Array of tuples `[signed_int32, query_frame_offset]`. Maximum 800 items per request.

#### Response: Match Found (200 OK)
```json
{
  "matched": true,
  "track": {
    "id": 4821,
    "title": "Bohemian Rhapsody",
    "artist": "Queen",
    "duration_seconds": 354,
    "offset_seconds": 42.18
  },
  "confidence": {
    "peak_votes": 84,
    "prominence_ratio": 9.33
  }
}
```

#### Response: Local Miss with Fallback Token (404 Not Found)
```json
{
  "matched": false,
  "fallback_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

---

### 2. Fallback Audio Recognition

Proxies compressed audio to commercial recognition providers (AudD / ACRCloud) using an authenticated single-use token issued on a local cache miss.

- **Method**: `POST`
- **Path**: `/v1/recognize/fallback`
- **Headers**:
  - `Authorization: Bearer <fallback_token>`
  - `Content-Type: audio/ogg` (or `audio/mpeg`, `audio/wav`)

#### Request Body
Binary audio buffer (typically 25 KB Opus/MP3 or 110 KB 16-bit PCM).

#### Response: Fallback Match Found (200 OK)
```json
{
  "matched": true,
  "provider": "audd",
  "track": {
    "title": "Midnight City",
    "artist": "M83",
    "album": "Hurry Up, We're Dreaming",
    "release_date": "2011-10-18"
  }
}
```

#### Response: Token Invalid or Already Consumed (401 Unauthorized)
```json
{
  "detail": "Invalid, expired, or already consumed fallback token"
}
```

---

### 3. Catalog Batch Ingestion (Internal / Admin)

Ingests pre-computed song landmarks into the PostgreSQL database.

- **Method**: `POST`
- **Path**: `/v1/catalog/ingest`
- **Content-Type**: `application/json`

#### Request Body
```json
{
  "title": "Track Title",
  "artist": "Artist Name",
  "duration_seconds": 210,
  "fingerprints": [
    [-142081920, 14],
    [89102341, 19]
  ]
}
```

#### Response (201 Created)
```json
{
  "song_id": 104,
  "inserted_fingerprints": 3412
}
```
