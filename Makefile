setup_local_db:
	@echo "Creating local database..."
	@atlas deployments setup local --type local --port 3307 --force
	@echo "Local database created."

start_local_db:
	@echo "Starting local database..."
	@atlas deployments start local
	@echo "Local database started."
