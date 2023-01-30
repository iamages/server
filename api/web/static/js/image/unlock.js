'use strict';

const descriptionElement = document.getElementById("description");
const imageElement = document.getElementById("image");
const lockedInfo = document.getElementById("locked-info");
const unlockKeyInput = document.getElementById("unlock-key-input");
const unlockButton = document.getElementById("unlock-button");
const unlockErrorSpan = document.getElementById("unlock-error-span");

const worker = new Worker("/api/private/static/js/image/decryption-worker.js");
worker.onmessage = function(e) {
  descriptionElement.innerText = e.data.metadata.description;
  infoModal.content.contentType.innerText = e.data.metadata.real_content_type;
  infoModal.content.dimensions.innerText = `${e.data.metadata.width}x${e.data.metadata.height}`;
  imageElement.src = URL.createObjectURL(e.data.image);
  lockedInfo.classList.add("is-hidden");
  imageElement.classList.remove("is-hidden");
  worker.terminate();
}
worker.onerror = function(e) {
  console.error(e.error);
  unlockErrorSpan.innerText = e.message;
  unlockErrorSpan.classList.remove("is-hidden");
  unlockKeyInput.disabled = false;
  unlockButton.classList.remove("is-loading");
  unlockButton.disabled = false;
}

unlockButton.onclick = function() {
  unlockErrorSpan.classList.add("is-hidden");
  unlockKeyInput.disabled = true;
  unlockButton.disabled = true;
  unlockButton.classList.add("is-loading");
  worker.postMessage({
    "id": image.id,
    "metadata": image.metadata,
    "key": unlockKeyInput.value,
    "downloadURL": downloadURL
  });
}

// Initialize button.
unlockButton.classList.remove("is-danger");
unlockButton.classList.add("is-success");
unlockButton.innerText = "Unlock";
unlockButton.disabled = false;