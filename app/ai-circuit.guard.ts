import { CanActivate, ExecutionContext, Injectable, ServiceUnavailableException } from "@nestjs/common";
import { Observable } from "rxjs";
import { AiStatusMonitoringService } from "../monitoring/ai-status-monitoring.service";

@Injectable()
export class AiCircuitGuard implements CanActivate {
  constructor(
    private readonly aiStatusMonitoringService: AiStatusMonitoringService
  ) { }

  canActivate(context: ExecutionContext): boolean {
    const isAvailable = this.aiStatusMonitoringService.isAvailable();
    if (!isAvailable) {
      throw new ServiceUnavailableException('AI Service is Currently Unavailable.');
    }
    return true;
  }
}