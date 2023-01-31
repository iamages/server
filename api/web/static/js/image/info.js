'use strict';

const relativeTime = new RelativeTime("en");

const infoButton = document.getElementById("info-button");

// Prep info modal
const infoModal = {
  controller: new BulmaModal("#info-modal"),
  content: {
    contentType: document.getElementById("info-modal-content-type"),
    dimensions: document.getElementById("info-modal-dimensions"),
    createdOn: document.getElementById("info-modal-created-on")
  }
}
if (!image.lock.is_locked) {
  infoModal.content.contentType.innerText = image.content_type;
  infoModal.content.dimensions.innerText = `${image.metadata.data.width}x${image.metadata.data.height}`;
} else {
  infoModal.content.contentType.innerText = "Unlock image to view";
  infoModal.content.dimensions.innerText = "Unlock image to view";
}
infoModal.content.createdOn.innerText = relativeTime.getRelativeTime(new Date(image.created_on));

// Initialize button
infoButton.disabled = false;

infoButton.onclick = function() {
  infoModal.controller.show();
}