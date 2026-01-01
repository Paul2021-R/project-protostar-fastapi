import { Module } from '@nestjs/common';
import { AppController } from './app.controller';
import { AppService } from './app.service';
import { PrismaService } from './prisma/prisma.service';
import { ConfigModule } from '@nestjs/config';
import { REDIS_CLIENT, RedisModule } from './common/redis/redis.module';
import { ChatModule } from './features/chat/chat.module';
import { SystemMonitoringService } from './common/monitoring/sytem-monitoring.service';
import { ThrottlerGuard, ThrottlerModule, seconds } from '@nestjs/throttler';
import { ThrottlerStorageRedisService } from '@nest-lab/throttler-storage-redis';
import { Redis } from 'ioredis';
import { APP_GUARD } from '@nestjs/core';
import { MonitoringModule } from './common/monitoring/monitoring.module';

@Module({
  imports: [
    ConfigModule.forRoot({
      isGlobal: true,
      envFilePath: '.env',
    }),
    RedisModule,
    MonitoringModule,
    ChatModule,
    ThrottlerModule.forRootAsync({
      imports: [RedisModule],
      inject: [REDIS_CLIENT],
      useFactory: (redis: Redis) => ({
        throttlers: [
          {
            name: 'short',
            ttl: seconds(1),
            limit: 10,
          },
          {
            name: 'medium',
            ttl: seconds(60),
            limit: 40,
          },
        ],
        errorMessage: 'Too many requests. Please try again later.',
        storage: new ThrottlerStorageRedisService(redis.duplicate()),
      }),
    }),
  ],
  controllers: [AppController],
  providers: [
    AppService,
    PrismaService,
    {
      provide: APP_GUARD,
      useClass: ThrottlerGuard,
    },
  ],
})
export class AppModule { }
