import React from 'react';
import { createRoot } from 'react-dom/client';
import 'esp-web-tools/dist/web/install-button.js';
import App from './App';
import './index.css';
createRoot(document.getElementById('root')).render(<React.StrictMode><App /></React.StrictMode>);
