#!/usr/bin/env bash

# ======================================================
# SEO POC Django Project Bootstrap Script
# ======================================================

PROJECT_NAME="seo_poc"
CONFIG_DIR="config"
APP_DIR="apps/seo"

echo "🚀 Creating Django SEO POC structure..."

# Root project
# mkdir -p $PROJECT_NAME
# cd $PROJECT_NAME || exit

# Create manage.py placeholder
touch manage.py

# Config folder
mkdir -p $CONFIG_DIR
touch $CONFIG_DIR/__init__.py
touch $CONFIG_DIR/settings.py
touch $CONFIG_DIR/urls.py
touch $CONFIG_DIR/celery.py

# Apps folder
mkdir -p apps
mkdir -p $APP_DIR

# Core app files
touch $APP_DIR/__init__.py
touch $APP_DIR/admin.py
touch $APP_DIR/apps.py
touch $APP_DIR/models.py
touch $APP_DIR/urls.py
touch $APP_DIR/views.py
touch $APP_DIR/serializers.py
touch $APP_DIR/selectors.py
touch $APP_DIR/constants.py
touch $APP_DIR/exceptions.py

# Services
mkdir -p $APP_DIR/services
touch $APP_DIR/services/__init__.py
touch $APP_DIR/services/run_orchestrator.py
touch $APP_DIR/services/fetcher.py
touch $APP_DIR/services/extractor.py
touch $APP_DIR/services/classifier.py
touch $APP_DIR/services/keywords.py
touch $APP_DIR/services/serp.py
touch $APP_DIR/services/analyzer.py
touch $APP_DIR/services/recommender.py

# Tasks
mkdir -p $APP_DIR/tasks
touch $APP_DIR/tasks/__init__.py
touch $APP_DIR/tasks/run.py
touch $APP_DIR/tasks/steps.py

# Providers
mkdir -p $APP_DIR/providers
touch $APP_DIR/providers/__init__.py
touch $APP_DIR/providers/serp_base.py
touch $APP_DIR/providers/serp_dataforseo.py

# Migrations
mkdir -p $APP_DIR/migrations
touch $APP_DIR/migrations/__init__.py

# Docs
mkdir -p docs
touch docs/seo_poc_spec.md
touch docs/run_steps.md

# Requirements
touch requirements.txt

echo "✅ Structure created successfully!"
echo ""
echo "📂 Created project tree:"
tree -L 4 2>/dev/null || find . -maxdepth 4 -type d

echo ""
echo "Next:"
echo "1. Create virtualenv"
echo "2. pip install django djangorestframework celery redis"
echo "3. Add app to INSTALLED_APPS"
echo "4. Configure database"
echo "5. Start implementing models"