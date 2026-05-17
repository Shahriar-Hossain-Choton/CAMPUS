/* threads.js — JS only where strictly necessary:
   1. Auto-scroll message list to latest message on load
   2. Photo preview with per-image remove buttons
   3. File count badge next to attach label
   4. Enter key to send message (Shift + Enter for new line)
   5. AJAX submission to avoid full page refresh (with closed-thread detection)
   6. Background Polling for Recipient Real-time (with auto-refresh on session close)
*/

document.addEventListener('DOMContentLoaded', function () {

  /* ── 1. Scroll message list to bottom ─────────────────────── */
  var messageList = document.querySelector('.threads-message-list');
  if (messageList) {
    messageList.scrollTop = messageList.scrollHeight;
  }

  /* ── 2. Photo preview + removable thumbnails ──────────────── */
  var fileInput = document.getElementById('thread-photos');
  var preview = document.getElementById('thread-photo-preview');
  var countBadge = document.getElementById('thread-attach-count');

  var dt = new DataTransfer();

  if (fileInput && preview) {
    fileInput.addEventListener('change', function () {
      Array.from(this.files).forEach(function (file) {
        if (!file.type.startsWith('image/')) return;
        dt.items.add(file);
      });

      fileInput.files = dt.files;
      renderPreviews();
    });
  }

  function renderPreviews() {
    if (!preview) return;
    preview.innerHTML = '';

    Array.from(dt.files).forEach(function (file, index) {
      var item = document.createElement('div');
      item.className = 'threads-compose__preview-item';

      var img = document.createElement('img');
      img.alt = file.name;

      var reader = new FileReader();
      reader.onload = function (e) { img.src = e.target.result; };
      reader.readAsDataURL(file);

      var remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'threads-compose__preview-remove';
      remove.textContent = '×';
      remove.setAttribute('aria-label', 'Remove ' + file.name);

      remove.addEventListener('click', function () {
        dt.items.remove(index);
        fileInput.files = dt.files;
        renderPreviews();
      });

      item.appendChild(img);
      item.appendChild(remove);
      preview.appendChild(item);
    });

    if (countBadge) {
      countBadge.textContent = dt.files.length > 0 ? '(' + dt.files.length + ' photos ready)' : '';
    }
  }

  /* ── 3. Enter key to send message ─────────────────────────── */
  var messageTextarea = document.querySelector('#message-list ~ form textarea') || document.querySelector('form textarea');

  if (messageTextarea) {
    messageTextarea.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();

        var form = this.closest('form');
        if (form) {
          var submitButton = form.querySelector('button[type="submit"]');
          if (submitButton) {
            submitButton.click();
          } else {
            form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
          }
        }
      }
    });
  }

  /* ── 4. AJAX Form Submission (With Closed-Thread Interception) ── */
  var messageForm = document.querySelector('#message-list ~ form') || document.querySelector('form');

  if (messageForm) {
    messageForm.addEventListener('submit', function (e) {
      e.preventDefault();

      var form = this;
      var formData = new FormData(form);
      var actionUrl = form.getAttribute('action') || window.location.href;

      var submitBtn = form.querySelector('button[type="submit"]');
      if (submitBtn) submitBtn.disabled = true;

      fetch(actionUrl, {
        method: 'POST',
        body: formData,
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
      })
        .then(function (response) {
          if (!response.ok) throw new Error('Network response error');
          return response.text();
        })
        .then(function (htmlString) {
          var parser = new DOMParser();
          var doc = parser.parseFromString(htmlString, 'text/html');

          // CRITICAL CHECK: Does the message input form still exist in the server's response?
          var incomingForm = doc.querySelector('#message-list ~ form') || doc.querySelector('form textarea');

          if (!incomingForm) {
            // The backend view caught the error, added the Django message, and redirected!
            // Swapping the full body displays Django's error alert banner and hides the compose layout.
            document.body.innerHTML = doc.body.innerHTML;
            return;
          }

          // Regular update if thread is still open
          var newContent = doc.getElementById('message-list') || doc.querySelector('.threads-message-list');
          var currentList = document.getElementById('message-list') || document.querySelector('.threads-message-list');

          if (newContent && currentList) {
            currentList.innerHTML = newContent.innerHTML;
            currentList.scrollTop = currentList.scrollHeight;
          }

          form.reset();
          dt = new DataTransfer();
          if (fileInput) fileInput.files = dt.files;
          renderPreviews();
        })
        .catch(function (error) {
          console.error('Error sending message:', error);
        })
        .finally(function () {
          if (submitBtn) submitBtn.disabled = false;
        });
    });
  }

  /* ── 5. Background Polling (With Real-Time Close Detection) ── */
  
  // Look specifically for the message TEXTAREA, not just any form.
  var messageTextarea = document.querySelector('#message-list ~ form textarea') || document.querySelector('form textarea');
  
  // ONLY start the polling engine if the thread is currently OPEN (textarea exists)
  if (messageTextarea) {
    var currentUrl = window.location.href;
    var pingSound = new Audio('/static/sounds/duck.mp3'); 
    pingSound.volume = 0.6;

    function pollNewMessages() {
      if (dt && dt.files.length > 0) return; 
      
      fetch(currentUrl, {
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
      })
      .then(function (response) {
        if (response.ok) return response.text();
      })
      .then(function (htmlString) {
        var parser = new DOMParser();
        var doc = parser.parseFromString(htmlString, 'text/html');
        
        // CRITICAL CHECK: Does the incoming HTML still have a message textarea?
        var incomingTextarea = doc.querySelector('#message-list ~ form textarea') || doc.querySelector('form textarea');
        
        if (!incomingTextarea) {
          // The textarea disappeared! The other user closed the thread.
          // Reload the page once. When it reloads, messageTextarea will be null, and polling will never start again.
          window.location.reload();
          return;
        }
        
        var newContent = doc.getElementById('message-list') || doc.querySelector('.threads-message-list');
        var currentList = document.getElementById('message-list') || document.querySelector('.threads-message-list');
        
        if (newContent && currentList) {
          var currentCount = currentList.querySelectorAll('.threads-message').length;
          var incomingMessages = newContent.querySelectorAll('.threads-message');
          var newCount = incomingMessages.length;
          
          if (newCount > currentCount) {
            var latestMessage = incomingMessages[incomingMessages.length - 1];
            var isPartnerMessage = latestMessage ? !latestMessage.classList.contains('threads-message--own') : false;
            var isAtBottom = (currentList.scrollHeight - currentList.scrollTop <= currentList.clientHeight + 100);
            
            currentList.innerHTML = newContent.innerHTML;
            
            if (isAtBottom) {
              currentList.scrollTop = currentList.scrollHeight; 
            }

            if (isPartnerMessage) {
              pingSound.play().catch(function(e) { console.log("Audio block context:", e); });
            }
          }
        }
      })
      .catch(function (err) {
        console.warn("Polling error:", err);
      });
    }

    var pollingInterval = setInterval(pollNewMessages, 4000);

    document.addEventListener('visibilitychange', function() {
      if (document.hidden) {
        clearInterval(pollingInterval);
      } else {
        pollingInterval = setInterval(pollNewMessages, 4000);
      }
    });
  }

});