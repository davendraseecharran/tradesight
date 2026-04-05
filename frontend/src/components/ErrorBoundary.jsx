import { Component } from 'react'

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="card flex items-center justify-center py-8 text-center">
          <div>
            <p className="text-warn text-sm font-medium mb-1">Component Error</p>
            <p className="text-xs text-text-muted">{this.state.error?.message || 'Something went wrong'}</p>
            <button
              onClick={() => this.setState({ hasError: false, error: null })}
              className="btn-secondary text-xs mt-3"
            >
              Retry
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
