interface ProtectedRouteProps {
  children: JSX.Element;
  requiredRole?: 'admin' | 'moderator' | 'user';
}

const ProtectedRoute = ({ children }: ProtectedRouteProps) => {
  // Authentication is bypassed for the local tool.
  return children;
};

export default ProtectedRoute;