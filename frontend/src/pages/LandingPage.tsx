import { Link } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'

export default function LandingPage() {
  const { isAuthenticated } = useAuthStore()

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
      <div className="container mx-auto px-4 py-16">
        <nav className="flex justify-between items-center mb-16">
          <h1 className="text-3xl font-bold text-gray-900">Miaobu</h1>
          <div>
            {isAuthenticated ? (
              <Link
                to="/dashboard"
                className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 transition"
              >
                Dashboard
              </Link>
            ) : (
              <Link
                to="/login"
                className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 transition"
              >
                Sign In
              </Link>
            )}
          </div>
        </nav>

        <div className="text-center max-w-4xl mx-auto">
          <h2 className="text-5xl font-bold text-gray-900 mb-6">
            Deploy Your Frontend
            <br />
            <span className="text-blue-600">To Alibaba Cloud</span>
          </h2>
          <p className="text-xl text-gray-600 mb-8">
            Connect your GitHub repository, and we'll build and deploy your static site
            to Alibaba Cloud OSS + CDN with automatic SSL certificates.
          </p>
          <div className="flex gap-4 justify-center">
            {!isAuthenticated && (
              <Link
                to="/login"
                className="bg-blue-600 text-white px-8 py-3 rounded-lg text-lg font-semibold hover:bg-blue-700 transition"
              >
                Get Started for Free
              </Link>
            )}
          </div>
        </div>

        <div className="mt-20 grid md:grid-cols-3 gap-8 max-w-6xl mx-auto">
          <div className="bg-white p-6 rounded-xl shadow-md">
            <div className="text-3xl mb-4">🚀</div>
            <h3 className="text-xl font-bold mb-2">Instant Deploys</h3>
            <p className="text-gray-600">
              Push to GitHub and your site goes live automatically
            </p>
          </div>
          <div className="bg-white p-6 rounded-xl shadow-md">
            <div className="text-3xl mb-4">🔒</div>
            <h3 className="text-xl font-bold mb-2">Automatic SSL</h3>
            <p className="text-gray-600">
              Free SSL certificates via Let's Encrypt for all domains
            </p>
          </div>
          <div className="bg-white p-6 rounded-xl shadow-md">
            <div className="text-3xl mb-4">⚡</div>
            <h3 className="text-xl font-bold mb-2">CDN Accelerated</h3>
            <p className="text-gray-600">
              Global CDN ensures fast loading times everywhere
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
