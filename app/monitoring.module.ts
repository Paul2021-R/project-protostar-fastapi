import { Module } from '@nestjs/common';
import { RedisModule } from '../redis/redis.module';
import { AiStatusMonitoringService } from './ai-status-monitoring.service';
import { SystemMonitoringService } from './sytem-monitoring.service';
import { ScheduleModule } from '@nestjs/schedule';

@Module({
  imports: [ScheduleModule.forRoot(), RedisModule],
  providers: [AiStatusMonitoringService, SystemMonitoringService],
  exports: [AiStatusMonitoringService, SystemMonitoringService],
})
export class MonitoringModule {}
