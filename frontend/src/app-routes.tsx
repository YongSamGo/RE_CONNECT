import App from './App'
import { RuntimeFailure } from './ui/RuntimeFailure'

// Data routers catch render/lazy errors before the outer React error boundary.
export const appRoutes = [{ path: '*', element: <App />, errorElement: <RuntimeFailure /> }]
