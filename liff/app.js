let userLineId = "";

async function initializeLiff() {
    try {
        const configRes = await fetch('/api/config');
        const config = await configRes.json();
        const liffId = config.liffId;

        if (!liffId || liffId.trim() === '') {
            throw new Error("LIFF ID not configured on server.");
        }

        await liff.init({ liffId: liffId });
        if (!liff.isLoggedIn()) {
            liff.login();
            return;
        }
        
        const profile = await liff.getProfile();
        userLineId = profile.userId;
        
        document.getElementById('profile-img').src = profile.pictureUrl || 'https://via.placeholder.com/40';
        document.getElementById('profile-name').textContent = `哈囉, ${profile.displayName}`;
        
        document.getElementById('loading').classList.add('hidden');
        document.getElementById('profile-section').classList.remove('hidden');
        document.getElementById('bind-form').classList.remove('hidden');
        
    } catch (err) {
        console.error('LIFF Init Error:', err);
        showMessage('初始化失敗，請確認 LIFF ID 設定', 'error');
        // Fallback for local testing without LIFF
        userLineId = "mock_line_user_id_" + Math.random().toString(36).substring(7);
        document.getElementById('loading').classList.add('hidden');
        document.getElementById('bind-form').classList.remove('hidden');
        showMessage('使用本地測試模式 (非 LINE 環境)', 'success');
    }
}



document.getElementById('btn-bind').addEventListener('click', async () => {
    const phone = document.getElementById('phone').value;
    
    if (!phone || phone.length < 10) {
        showMessage('請填寫完整手機號碼', 'error');
        return;
    }
    
    try {
        const res = await fetch('/api/bind', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ phone_number: phone, line_user_id: userLineId })
        });
        
        if (res.ok) {
            document.getElementById('bind-form').classList.add('hidden');
            document.getElementById('profile-section').classList.add('hidden');
            document.getElementById('success-state').classList.remove('hidden');
        } else {
            const data = await res.json();
            showMessage(data.detail || '綁定失敗', 'error');
        }
    } catch (err) {
        showMessage('網路錯誤', 'error');
    }
});

document.getElementById('btn-close').addEventListener('click', () => {
    try {
        liff.closeWindow();
    } catch (e) {
        alert("測試模式：關閉視窗");
    }
});

function showMessage(text, type) {
    const msg = document.getElementById('message-area');
    msg.textContent = text;
    msg.className = `message ${type}`;
}

// Start
initializeLiff();
