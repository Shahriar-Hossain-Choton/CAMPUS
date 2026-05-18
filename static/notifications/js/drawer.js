(function () {
  function getCookie(name) {
    var cookieValue = null;
    if (document.cookie && document.cookie !== '') {
      var cookies = document.cookie.split(';');
      for (var i = 0; i < cookies.length; i++) {
        var cookie = cookies[i].trim();
        if (cookie.substring(0, name.length + 1) === (name + '=')) {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }

  const badge = document.getElementById('notif-badge');
  const dropdown = document.getElementById('notif-dropdown');
  const notifBtn = dropdown ? dropdown.querySelector('.notif-btn') : null;
  const listContainer = document.querySelector('#notif-list .notif-items'); 

  if (!badge || !dropdown || !notifBtn || !listContainer) return;

  function fetchUnread() {
    fetch('/notifications/unread_count/')
      .then(r => r.json())
      .then(data => {
        const c = data.count || 0;
        badge.textContent = c > 99 ? '99+' : c;
        badge.style.display = c > 0 ? 'inline-block' : 'none';
      })
      .catch(() => {});
  }

  function fetchList() {
    listContainer.innerHTML = '<div class="notif-empty">Loading...</div>';

    fetch('/notifications/list/?limit=20')
      .then(r => r.json())
      .then(data => {
        const items = data.notifications || [];
        listContainer.innerHTML = '';
        
        if (items.length === 0) {
          listContainer.innerHTML = '<div class="notif-empty">No notifications</div>';
          return;
        }

        items.forEach(n => {
          const hasUrl = n.data && n.data.url;
          const el = document.createElement(hasUrl ? 'a' : 'div');
          
          el.className = 'notif-item' + (n.read ? '' : ' notif-unread');
          el.dataset.id = n.id;
          
          if (hasUrl) {
            el.href = n.data.url;
            el.style.display = 'block'; 
            el.style.textDecoration = 'none';
            el.style.color = 'inherit';
          }
          
          const dateObj = new Date(n.created_at);
          const dateStr = dateObj.toLocaleDateString(undefined, { 
            month: 'short', day: 'numeric' 
          }) + ' at ' + dateObj.toLocaleTimeString(undefined, { 
            hour: '2-digit', minute: '2-digit' 
          });

          el.innerHTML = `
            <div class="notif-verb">${n.verb || ''}</div>
            <div class="notif-meta">${dateStr}</div>
          `;
          listContainer.appendChild(el);
        });
      })
      .catch(() => {
        listContainer.innerHTML = '<div class="notif-empty">Failed to load notifications.</div>';
      });
  }

  // Toggle Dropdown
  notifBtn.addEventListener('click', function (e) {
    e.stopPropagation(); 
    dropdown.classList.toggle('open');
    if (dropdown.classList.contains('open')) {
      // Fetch the full list when opened
      fetchList();
      
      // We also sync the unread badge again when they open the drawer 
      // just in case they navigated back/forward in their browser history.
      fetchUnread();
    }
  });

  // Mark individual notification as read when clicked
  listContainer.addEventListener('click', function(e) {
    const item = e.target.closest('.notif-item');
    if (!item) return;

    const isLink = item.tagName.toLowerCase() === 'a';
    const href = item.getAttribute('href');

    if (!item.classList.contains('notif-unread')) return;

    if (isLink && href) {
      e.preventDefault(); 
    }

    const notifId = item.dataset.id;
    const csrftoken = getCookie('csrftoken');

    fetch('/notifications/mark_read/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrftoken
      },
      body: JSON.stringify({ id: notifId })
    }).finally(() => {
      item.classList.remove('notif-unread');
      
      let currentCount = parseInt(badge.textContent) || 0;
      if (currentCount > 0) {
        currentCount--;
        badge.textContent = currentCount > 99 ? '99+' : currentCount;
        if (currentCount === 0) badge.style.display = 'none';
      }

      if (isLink && href) {
        window.location.href = href;
      }
    });
  });

  dropdown.querySelector('.notif-list').addEventListener('click', function(e) {
    e.stopPropagation();
  });

  document.addEventListener('click', function(e) {
    if (dropdown.classList.contains('open')) {
      dropdown.classList.remove('open');
    }
  });

  // Fetch immediately on page load, then stop (No more polling)
  fetchUnread();
})();