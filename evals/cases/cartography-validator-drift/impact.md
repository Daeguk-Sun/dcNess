# Build impact

App lifecycle wiring now starts and stops the existing MessageObserver. The owner remains the data module. This adds the as-built edge `App -> MessageObserver` and changes the observer capability from planned to landed based on `AppObserverIntegrationTest`.
