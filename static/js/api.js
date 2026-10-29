/* api.js — thin JSON wrapper around fetch.
 * Always sends the session cookie, parses JSON errors into ApiError-shaped
 * Error objects, and broadcasts 'auth:required' when the session has ended. */
const api = (() => {
    async function request(method, path, body) {
        const options = {
            method,
            credentials: 'same-origin',
            headers: { Accept: 'application/json' },
        };
        if (body !== undefined) {
            options.headers['Content-Type'] = 'application/json';
            options.body = JSON.stringify(body);
        }

        let response;
        try {
            response = await fetch(path, options);
        } catch (networkError) {
            const error = new Error('Cannot reach the server. Is it still running?');
            error.code = 'network';
            throw error;
        }

        if (response.status === 401) {
            window.dispatchEvent(new CustomEvent('auth:required'));
        }

        let data = null;
        const text = await response.text();
        if (text) {
            try {
                data = JSON.parse(text);
            } catch (parseError) {
                data = null;
            }
        }

        if (!response.ok) {
            const error = new Error((data && data.error) || `Request failed (${response.status})`);
            error.status = response.status;
            error.code = data && data.code;
            throw error;
        }
        return data;
    }

    return {
        get: (path) => request('GET', path),
        post: (path, body = {}) => request('POST', path, body),
        put: (path, body = {}) => request('PUT', path, body),
        del: (path) => request('DELETE', path),
    };
})();
