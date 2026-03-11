def failureStage = "Unknown"

pipeline {
    agent none

    environment {
        GHCR_CREDS_ID = 'ghcr-creds'
        GITHUB_CREDS_ID = 'github-creds'
        DISCORD_CREDS_ID = 'discord-webhook-url'
        IMAGE_NAME = 'ghcr.io/paul2021-r/project-protostar-fastapi'
        GITOPS_REPO = 'https://github.com/paul2021-r/project-gitops.git'
        GITOPS_PATH = 'protostar/backend/fastapi/overlays/prod/kustomization.yaml'
    }

    stages {
        stage('Checkout') {
            agent { label 'built-in' }
            steps {
                script {
                    try {
                        git credentialsId: GITHUB_CREDS_ID,
                            url: 'https://github.com/paul2021-r/project-protostar-fastapi.git',
                            branch: 'main'
                    } catch (Exception e) {
                        failureStage = "Checkout"
                        throw e
                    }
                }
            }
        }

        stage('Build & Push Image') {
            agent {
                kubernetes {
                    inheritFrom 'kaniko-agent'
                }
            }
            steps {
                script {
                    try {
                        checkout scm
                        container('kaniko') {
                            sh """
                                /kaniko/executor \
                                --context=dir:///workspace/workspace/protostar-fastapi/app \
                                --dockerfile=/workspace/workspace/protostar-fastapi/app/Dockerfile \
                                --destination=${IMAGE_NAME}:${BUILD_NUMBER} \
                                --cache=true
                            """
                        }
                    } catch (Exception e) {
                        failureStage = "Build & Push Image"
                        throw e
                    }
                }
            }
        }

        stage('Update GitOps') {
            agent { label 'built-in' }
            steps {
                script {
                    try {
                        withCredentials([usernamePassword(
                            credentialsId: GITHUB_CREDS_ID,
                            usernameVariable: 'GIT_USER',
                            passwordVariable: 'GIT_TOKEN'
                        )]) {
                            sh """
                                git clone https://${GIT_USER}:${GIT_TOKEN}@github.com/paul2021-r/project-gitops.git gitops-repo
                                cd gitops-repo
                                sed -i 's/newTag: .*/newTag: "${BUILD_NUMBER}"/' ${GITOPS_PATH}
                                git config user.email "jenkins@protostar.com"
                                git config user.name "Jenkins"
                                git add ${GITOPS_PATH}
                                git commit -m "chore: update fastapi image tag to ${BUILD_NUMBER}"
                                git push
                            """
                        }
                    } catch (Exception e) {
                        failureStage = "Update GitOps"
                        throw e
                    }
                }
            }
        }
    }

    post {
        success {
            node('built-in') {
                script {
                    withCredentials([string(credentialsId: DISCORD_CREDS_ID, variable: 'DISCORD_URL')]) {
                        def message = "{\"content\": \"🚀 Build succeeded : **[${env.JOB_NAME}]** - **#${env.BUILD_NUMBER}**\"}"
                        sh "curl -X POST -H 'Content-Type: application/json' --data '${message}' ${DISCORD_URL}"
                    }
                }
            }
        }
        failure {
            node('built-in') {
                script {
                    withCredentials([string(credentialsId: DISCORD_CREDS_ID, variable: 'DISCORD_URL')]) {
                        def message = "{\"content\": \"🔥 Build failed at ${failureStage} : **[${env.JOB_NAME}]** - **#${env.BUILD_NUMBER}** ${env.BUILD_URL}\"}"
                        sh "curl -X POST -H 'Content-Type: application/json' --data '${message}' ${DISCORD_URL}"
                    }
                }
            }
        }
    }
}