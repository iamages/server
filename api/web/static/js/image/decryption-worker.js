'use strict';

importScripts(
  "/api/private/static/js/lib/argon2-bundled.min.js"
);

function b64decode(b64) {
  return Uint8Array.from(atob(b64), c => c.charCodeAt(0))
}

function unlock(key, salt, nonce, data, tag) {
  const alg = {
    name: "AES-GCM",
    iv: nonce
  }
  return argon2.hash({
    pass: key,
    salt: salt,
    time: 3,
    mem: 65536,
    parallelism: 4,
    hashLen: 16,
    type: argon2.ArgonType.Argon2id
  })
  .then(h =>  crypto.subtle.importKey("raw", h.hash, alg, false, ["decrypt"]))
  .then(key => {
    // Prepare ciphertext
    let ciphertext = new Uint8Array(data.length + tag.length);
    ciphertext.set(data);
    ciphertext.set(tag, data.length);

    return crypto.subtle.decrypt(alg, key, ciphertext)
  })
}

onmessage = function(e) {
  // Decrypted metadata object
  let metadata;
  // Data for image decryption
  let imageLock = {}

  unlock(
    e.data.key,
    b64decode(e.data.metadata.salt),
    b64decode(e.data.metadata.nonce),
    b64decode(e.data.metadata.data),
    b64decode(e.data.metadata.tag)
  )
  .then(raw =>  metadata = JSON.parse(new TextDecoder().decode(raw)))
  .then(() => fetch(e.data.downloadURL))
  .then(response => {
    imageLock.salt = b64decode(response.headers.get("X-Iamages-Lock-Salt"));
    imageLock.nonce = b64decode(response.headers.get("X-Iamages-Lock-Nonce"));
    imageLock.tag = b64decode(response.headers.get("X-Iamages-Lock-Tag"));
    return response.arrayBuffer()
  })
  .then(buffer => unlock(e.data.key, imageLock.salt, imageLock.nonce, new Uint8Array(buffer), imageLock.tag))
  .then(raw => {
    postMessage({
      metadata,
      image: new Blob([raw])
    })
  });
}