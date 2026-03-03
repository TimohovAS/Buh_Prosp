import React, { useState, useEffect } from 'react';

export default function ToastProvider() {
    const [toasts, setToasts] = useState([]);

    useEffect(() => {
        const handleApiError = (e) => {
            const newToast = { id: Date.now(), message: e.detail, type: 'error' };
            setToasts(prev => [...prev, newToast]);
            setTimeout(() => {
                setToasts(prev => prev.filter(t => t.id !== newToast.id));
            }, 5000);
        };

        const handleSuccess = (e) => {
            const newToast = { id: Date.now(), message: e.detail, type: 'success' };
            setToasts(prev => [...prev, newToast]);
            setTimeout(() => {
                setToasts(prev => prev.filter(t => t.id !== newToast.id));
            }, 3000);
        };

        window.addEventListener('api-error', handleApiError);
        window.addEventListener('api-success', handleSuccess);
        return () => {
            window.removeEventListener('api-error', handleApiError);
            window.removeEventListener('api-success', handleSuccess);
        };
    }, []);

    if (toasts.length === 0) return null;

    return (
        <div style={{
            position: 'fixed',
            bottom: '20px',
            right: '20px',
            zIndex: 9999,
            display: 'flex',
            flexDirection: 'column',
            gap: '10px'
        }}>
            {toasts.map(t => (
                <div key={t.id} style={{
                    backgroundColor: t.type === 'error' ? '#fee2e2' : '#dcfce7',
                    color: t.type === 'error' ? '#991b1b' : '#166534',
                    padding: '12px 16px',
                    borderRadius: '6px',
                    boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)',
                    minWidth: '250px',
                    maxWidth: '400px',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'flex-start',
                    borderLeft: `4px solid ${t.type === 'error' ? '#ef4444' : '#22c55e'}`
                }}>
                    <div>{t.message}</div>
                    <button
                        onClick={() => setToasts(prev => prev.filter(x => x.id !== t.id))}
                        style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: '0 4px', color: 'inherit', opacity: 0.5, fontSize: '18px', lineHeight: 1 }}
                    >
                        ×
                    </button>
                </div>
            ))}
        </div>
    );
}
