class AuthManager {
    constructor(verifyUrl, onSuccess) {
        this.verifyUrl = verifyUrl;
        this.onSuccess = onSuccess;
        this.currentToken = sessionStorage.getItem('ADMIN_TOKEN') || '';
        this.loginSection = document.getElementById('loginSection');
        this.dashboardSection = document.getElementById('dashboardSection');
        this.adminTokenInput = document.getElementById('adminToken');
        this.loginBtn = document.getElementById('loginBtn');
        this.loginStatus = document.getElementById('loginStatus');

        if (this.loginBtn) {
            this.loginBtn.addEventListener('click', () => this.handleLoginClick());
        }

        if (this.currentToken && this.adminTokenInput) {
            this.adminTokenInput.value = this.currentToken;
            this.attemptLogin(this.currentToken);
        }
    }

    showStatus(message, isError = false) {
        if (!this.loginStatus) return;
        this.loginStatus.textContent = message;
        this.loginStatus.className = 'status-message ' + (isError ? 'error' : 'success');
    }

    handleLoginClick() {
        const token = this.adminTokenInput.value.trim();
        if (!token) {
            this.showStatus('請輸入密碼！', true);
            return;
        }
        this.attemptLogin(token);
    }

    async attemptLogin(token) {
        try {
            const res = await fetch(this.verifyUrl, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (!res.ok) throw new Error("密碼錯誤");
            
            let data = null;
            // If the endpoint returns JSON, parse it (useful for fetching initial data during login)
            const contentType = res.headers.get("content-type");
            if (contentType && contentType.indexOf("application/json") !== -1) {
                data = await res.json();
            }

            this.currentToken = token;
            sessionStorage.setItem('ADMIN_TOKEN', token);
            
            if (this.loginSection) this.loginSection.classList.add('hidden');
            if (this.dashboardSection) this.dashboardSection.classList.remove('hidden');
            
            if (this.onSuccess) {
                this.onSuccess(data, token);
            }
        } catch (e) {
            this.showStatus('❌ 驗證失敗：' + e.message, true);
        }
    }
}

window.AuthManager = AuthManager;
